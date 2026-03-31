module GuiRuntimeOverride

export load_runtime_override, runtime_params, get_float, get_int, get_bool, get_string


mutable struct JsonParser
    text::String
    index::Int
end


function _peek(parser::JsonParser)
    parser.index > lastindex(parser.text) && return '\0'
    return parser.text[parser.index]
end


function _advance!(parser::JsonParser)
    parser.index = nextind(parser.text, parser.index)
    return parser
end


function _skip_ws!(parser::JsonParser)
    while isspace(_peek(parser))
        _advance!(parser)
    end
    return parser
end


function _expect!(parser::JsonParser, ch::Char)
    _skip_ws!(parser)
    _peek(parser) == ch || error("Invalid JSON: expected $(repr(ch))")
    _advance!(parser)
    return nothing
end


function _parse_string(parser::JsonParser)
    _expect!(parser, '"')
    buffer = IOBuffer()
    while true
        ch = _peek(parser)
        ch == '\0' && error("Invalid JSON: unterminated string")
        _advance!(parser)
        if ch == '"'
            return String(take!(buffer))
        elseif ch == '\\'
            esc = _peek(parser)
            esc == '\0' && error("Invalid JSON: bad escape")
            _advance!(parser)
            if esc == '"' || esc == '\\' || esc == '/'
                print(buffer, esc)
            elseif esc == 'b'
                print(buffer, '\b')
            elseif esc == 'f'
                print(buffer, '\f')
            elseif esc == 'n'
                print(buffer, '\n')
            elseif esc == 'r'
                print(buffer, '\r')
            elseif esc == 't'
                print(buffer, '\t')
            else
                error("Invalid JSON escape: \\$(esc)")
            end
        else
            print(buffer, ch)
        end
    end
end


function _parse_literal(parser::JsonParser, literal::String, value)
    for ch in literal
        _peek(parser) == ch || error("Invalid JSON literal: $(literal)")
        _advance!(parser)
    end
    return value
end


function _parse_number(parser::JsonParser)
    _skip_ws!(parser)
    start = parser.index
    while true
        ch = _peek(parser)
        if ch in ('0':'9') || ch in ('-', '+', '.', 'e', 'E')
            _advance!(parser)
        else
            break
        end
    end
    token = parser.text[start:prevind(parser.text, parser.index)]
    if occursin(r"[\.eE]", token)
        return parse(Float64, token)
    end
    return parse(Int, token)
end


function _parse_array(parser::JsonParser)
    values = Any[]
    _expect!(parser, '[')
    _skip_ws!(parser)
    if _peek(parser) == ']'
        _advance!(parser)
        return values
    end
    while true
        push!(values, _parse_value(parser))
        _skip_ws!(parser)
        if _peek(parser) == ']'
            _advance!(parser)
            return values
        end
        _expect!(parser, ',')
    end
end


function _parse_object(parser::JsonParser)
    values = Dict{String,Any}()
    _expect!(parser, '{')
    _skip_ws!(parser)
    if _peek(parser) == '}'
        _advance!(parser)
        return values
    end
    while true
        key = _parse_string(parser)
        _expect!(parser, ':')
        values[key] = _parse_value(parser)
        _skip_ws!(parser)
        if _peek(parser) == '}'
            _advance!(parser)
            return values
        end
        _expect!(parser, ',')
    end
end


function _parse_value(parser::JsonParser)
    _skip_ws!(parser)
    ch = _peek(parser)
    ch == '{' && return _parse_object(parser)
    ch == '[' && return _parse_array(parser)
    ch == '"' && return _parse_string(parser)
    ch == 't' && return _parse_literal(parser, "true", true)
    ch == 'f' && return _parse_literal(parser, "false", false)
    ch == 'n' && return _parse_literal(parser, "null", nothing)
    return _parse_number(parser)
end


function load_runtime_override(args)::Dict{String,Any}
    isempty(args) && return Dict{String,Any}()
    path = args[1]
    isfile(path) || return Dict{String,Any}()
    parser = JsonParser(read(path, String), 1)
    payload = _parse_value(parser)
    payload isa Dict{String,Any} || error("Runtime override must be a JSON object")
    return payload
end


function runtime_params(payload)::Dict{String,Any}
    params = get(payload, "params", Dict{String,Any}())
    params isa Dict{String,Any} || return Dict{String,Any}()
    return params
end


function _coerce_float(value, default::Float64)
    value === nothing && return default
    value isa Number && return Float64(value)
    value isa String && return parse(Float64, value)
    return default
end


function _coerce_int(value, default::Int)
    value === nothing && return default
    value isa Integer && return Int(value)
    value isa Number && return round(Int, value)
    value isa String && return parse(Int, value)
    return default
end


function _coerce_bool(value, default::Bool)
    value === nothing && return default
    value isa Bool && return value
    value isa Number && return value != 0
    if value isa String
        lowered = lowercase(strip(value))
        lowered in ("1", "true", "yes", "on") && return true
        lowered in ("0", "false", "no", "off") && return false
    end
    return default
end


function get_float(payload::Dict{String,Any}, key::String, default)
    return _coerce_float(get(payload, key, nothing), Float64(default))
end


function get_int(payload::Dict{String,Any}, key::String, default::Int)
    return _coerce_int(get(payload, key, nothing), default)
end


function get_bool(payload::Dict{String,Any}, key::String, default::Bool)
    return _coerce_bool(get(payload, key, nothing), default)
end


function get_string(payload::Dict{String,Any}, key::String, default::String)
    value = get(payload, key, nothing)
    value === nothing && return default
    return string(value)
end


end
