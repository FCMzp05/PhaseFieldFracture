# GUI 开发任务说明

---

## 你需要做什么（总体任务）

我有一套用 **Julia 语言**写的相场断裂仿真代码，目前只能在命令行运行，每次都要手动修改代码里的参数才能换一个工况。我希望你帮我在这套代码的基础上，做一个带图形界面的程序（GUI），让使用者可以通过界面填写参数、点击运行、实时看到结果。

**你不需要理解相场力学的物理含义。** 你只需要把这套"输入一堆参数 → 跑一段时间 → 输出结果图"的程序，套上一个可视化的壳子。

---

## 现有代码：每个文件详解

代码放在：`/Users/zhangpeng/Desktop/PFM-paper/code/`

共 5 个 Julia 脚本，下面逐一介绍每个文件的内容、参数和结构。

---

### 文件 1：`Miehe2010_SENT_tension.jl` ——【最优先，先从这个开始】

**是什么：** 单边缺口拉伸试样（SENT）的弹性断裂仿真。这是最基础的算例，物理最简单，代码量最小，调试最方便。**GUI 的第一步就是把这个算例跑通。**

**几何：** 1×1 mm 的正方形薄板，左边中间有一条从左边界水平向右延伸 0.5 mm 的预制裂纹（切槽），顶边施加竖向向上的位移载荷，底边完全固定。

**加载方式：** 位移控制，逐步施加竖向位移，共约 1000 步，最大位移 0.008 mm。裂纹会从预制切槽尖端向右扩展，最终贯穿整个试样。

**代码里的关键 `const` 变量（这些就是 GUI 需要暴露的参数）：**

```julia
# 几何参数
const W        = 1.0        # 试样宽度 (mm)
const H        = 1.0        # 试样高度 (mm)
const a0       = 0.5        # 预裂纹长度 (mm)，从左边界到裂纹尖端

# 材料参数（注意：原始脚本用 λ_mat 和 G_mat，可以换算成 E 和 ν）
const λ_mat    = 121_150.0  # 第一拉梅常数 (MPa)
const G_mat    =  80_770.0  # 剪切模量 (MPa)
# 换算：E ≈ 210,950 MPa，ν ≈ 0.3

# 相场参数
const Gc       = 2.7        # 临界能量释放率 (N/mm)，控制断裂韧性
const l0       = 0.015      # 裂纹长度尺度 (mm)，控制裂纹带宽度
const η_k      = 0.0        # 数值稳定参数（通常不需要改）

# 网格参数
const h_fine   = 0.005      # 裂纹路径附近的细网格尺寸 (mm)
const h_coarse = 0.05       # 远场粗网格尺寸 (mm)

# 加载参数
const N_STEPS_COARSE = 500  # 前段粗加载步数
const Δu_coarse = 8.0e-6   # 前段每步位移增量 (mm)
const Δu_fine   = 8.0e-6   # 后段每步位移增量 (mm)
const u_end     = 8.0e-3   # 最大位移 (mm)，总步数 ≈ 1000

# 输出控制
const OUTPUT_DIR = "results_SENT_tension"  # 结果保存目录
```

**主要函数：**
- `create_mesh()` — 调用 Gmsh 生成网格，返回 `.msh` 文件路径
- `run_simulation()` — 主求解循环，一步一步施加位移，每步交替求解位移场和损伤场
- `plot_scalar_field_heatmap(...)` — 生成损伤场的伪彩色 PNG 图片

**输出：** 每若干步保存一张损伤场 PNG，以及 VTK 文件（`.vtu`）供 ParaView 打开，以及 F-u 数据的 CSV 文件，全部存到 `results_SENT_tension/` 目录下。

---

### 文件 2：`Miehe2010_SENS_shear.jl` ——【第二优先】

**是什么：** 单边缺口纯剪试样（SENS）的弹性断裂仿真。物理模型与文件 1 完全相同，只有**边界条件不同**：顶边施加的是水平剪切位移（而不是竖向拉伸位移），结果是裂纹会向右下角斜向扩展（混合模态断裂），这是这个算例的特色。

**几何：** 与 SENT 完全相同，1×1 mm 正方形板，同样的预制裂纹。

**加载方式：** 顶边施加水平位移（剪切），底边完全固定，左边竖向约束（防止刚体转动）。

**代码里的关键 `const` 变量：**

```julia
# 几何（与 SENT 相同）
const W        = 1.0
const H        = 1.0
const a0       = 0.5

# 材料（与 SENT 完全相同）
const λ_mat    = 121_150.0
const G_mat    =  80_770.0
const Gc       = 2.7
const l0       = 0.015
const η_k      = 0.0

# 网格（与 SENT 相同，但细化区域位置不同）
const h_fine   = 0.005
const h_coarse = 0.05

# 加载（注意：剪切步长更大，全程只用一个步长）
const Δu_shear = 2.0e-5    # 剪切方向每步增量 (mm)，全程恒定
const u_end    = 20.0e-3   # 最大水平位移 (mm)

const OUTPUT_DIR = "results_SENS_shear"
```

**与 SENT 的差异：** 这个脚本只有一个步长（不分粗细），因为剪切断裂过程比较平稳。边界条件部分代码略有不同（Dirichlet BC 施加方向不同）。其余代码结构几乎和 SENT 一样，改写 `gui_solver.jl` 时参考 SENT 改就行。

**输出：** 同样是 PNG + VTK + CSV，存到 `results_SENS_shear/`。

---

### 文件 3：`Carrara2020_SENT_fatigue_Fig6.jl` ——【疲劳算例，第三优先】

**是什么：** 弹性疲劳裂纹扩展仿真。与前两个脚本的最大区别是**载荷是循环的**（一上一下反复加载），而不是单调增加。程序会模拟裂纹在反复载荷下一点一点往前扩展，输出的是 a-N 曲线（裂纹长度 a 随循环数 N 的变化），而不是 F-u 曲线。

**几何：** 还是 SENT 试样，1×1 mm，同样的预制裂纹。

**加载方式：** 位移循环加载，每个循环分若干子步（`N_STEPS_PER_CYCLE = 8`）走完一个完整的加卸载过程，循环 `MAX_CYCLES = 9000` 次。支持不同的位移幅值（`Δu_ranges`）跑多条 a-N 曲线。

**代码里的关键 `const` 变量：**

```julia
# 几何（与 SENT 相同）
const W = 1.0;  const H = 1.0;  const a0 = 0.5

# 材料
const E_mat    = 210_000.0  # MPa（注意这里直接给 E，不用 λ/G）
const ν_mat    = 0.30
const Gc       = 2.70       # N/mm
const l0       = 0.004      # mm（比 SENT 更小！l₀ 值不一样）
const η_k      = 1e-10

# 疲劳参数
const αT       = ...        # 疲劳阈值，由 Gc/l0/E 自动计算，GUI 可以直接展示

# 加载参数
const Δu_ranges = [1.5e-3, 2.0e-3, 2.5e-3, 3.0e-3, 4.0e-3, 5.0e-3]
                            # 多组位移幅值，每组跑一条 a-N 曲线
                            # GUI 里让用户选一个值（或自己输入）
const MAX_CYCLES       = 9000   # 最大循环数（裂纹穿透前自动停止）
const N_STEPS_PER_CYCLE = 8    # 每个循环分几个子步

# 网格（与 SENT 相同）
const h_fine   = 0.005;  const h_coarse = 0.05

const OUTPUT_DIR = "results_Carrara2020_SENT_fatigue_Fig6"
```

**与前两个脚本最大的不同：**
1. 主循环是"循环数"而不是"步数"，输出的进度是"当前第几个循环 / 总循环数"
2. 输出曲线是 a-N（裂纹长度 vs 循环数），GUI 右下角的曲线图横纵轴要换成 N 和 a
3. 有裂纹长度提取函数（`extract_crack_length()`），每个循环结束时调用

**输出：** 最终的损伤场 PNG 和 VTK，以及 a-N 数据的 CSV，存到 `results_Carrara2020_SENT_fatigue_Fig6/`。

---

### 文件 4：`Fang2019_flat_grooved_H01E.jl` ——【塑性断裂算例】

**是什么：** 带圆弧缺口的平板（flat grooved specimen）弹塑性断裂仿真。与前三个最大的区别是**材料有塑性**（会产生永久变形），代码里增加了"返回映射算法"来处理塑性。

**几何：** 与前面的 SENT 完全不同！这是一个 18×50 mm 的长方形板，左右两侧各有一个圆弧缺口（不是预制裂纹），顶部施加拉伸位移。

**代码里的关键参数（注意：这个脚本用结构体 `MaterialData` 组织材料参数）：**

```julia
# 几何（注意：尺寸与 SENT 完全不同！）
const W          = 18.0    # 试样宽度 (mm)
const H_specimen = 50.0    # 试样高度 (mm)
const r_notch    = 2.5     # 缺口圆弧半径 (mm)

# 材料（通过 create_material(H_ratio=0.1) 创建结构体）
E      = 71_480.0   # MPa（注意：不是钢，比 SENT 的 E 小）
ν      = 0.3
σy0    = 345.0      # 屈服应力 (MPa)
H_hard = H_ratio * E  # 线性等向硬化模量（H_ratio = 0.1 表示 H = 0.1E）

# 相场参数
const lc      = 0.1     # 长度尺度 (mm)（这里变量名叫 lc 不叫 l0！）
const Gc      = 9.31    # N/mm（比 SENT 大很多！）
const η_stab  = 1e-4    # 数值稳定参数

# 加载
const u_total = 0.30    # 最大位移 (mm)
const N_STEPS = 1000    # 总步数

# 网格
const h_fine   = lc / 2 = 0.05   # mm（由 lc 决定）
const h_coarse = 3.0              # mm（远场粗网格，比 SENT 大很多）

const BASE_OUTPUT_DIR = "results_Fang2019_flat_grooved_scan"
```

**与前面脚本最大的不同：**
1. 几何完全不同，网格生成代码要重写（圆弧缺口，不是矩形切槽）
2. 有塑性，`run_simulation()` 内部每步要调用返回映射算法更新塑性状态
3. 材料用 `MaterialData` 结构体传递，不是全局 const
4. 这个脚本扫描三组硬化模量（`H_ratio = 0.1, 0.2, 0.5`），GUI 里让用户选一个就行

---

### 文件 5：`Li_fig9_paperstyle.jl` ——【最复杂，最后做】

**是什么：** SENT 试样的**弹塑性疲劳**裂纹扩展仿真。同时有塑性（文件 4 有）和疲劳（文件 3 有），是最复杂的一个。

**几何：** 回到 SENT，1×1 mm，与文件 1 相同的试样形状。

**代码里的关键参数：**

```julia
# 几何（与 SENT 相同）
const W = 1.0;  const H = 1.0;  const a0 = 0.5

# 材料（用 MaterialData 结构体，含塑性参数）
E    = 210_000.0    # MPa
ν    = 0.3
σy0  = 440.0        # 屈服应力 (MPa)
n    = 0.1          # 幂律硬化指数（不是线性硬化，是幂律！与文件4不同）

# 相场参数
const l0      = 0.02    # mm（与 SENT 弹性版的 0.015 略不同）
const Gc      = 2.7     # N/mm
const αT      = 11.25   # 疲劳阈值 (N/mm²)
const η_stab  = 1e-6
const η_plastic = 1.0   # 塑性能量权重系数

# 加载（循环加载，与文件3类似）
const u_max           = 0.001   # 最大位移幅值 (mm)
const R_load          = 0.0     # 载荷比（R=0 表示单边循环，最小位移=0）
const N_CYCLES        = 800     # 总循环数
const N_STEPS_PER_CYCLE = 20    # 每个循环分 20 个子步

# 输出控制
const SAVE_PNG_EVERY  = 10      # 每 10 个循环保存一张 PNG
```

**与其他脚本的综合对比：** 这个脚本融合了文件 3（疲劳循环加载，输出 a-N）和文件 4（返回映射塑性，含硬化），同时加了塑性能量对相场驱动力的贡献（`η_plastic` 系数）。代码量最大（1400+ 行），等文件 3 和 4 的 GUI 都调通了再来做这个。

---

## 五个脚本的对比总结

| 脚本 | 几何 | 有塑性 | 有疲劳 | 主要输出曲线 | 优先级 |
|------|------|--------|--------|-------------|--------|
| `Miehe2010_SENT_tension.jl` | SENT 1×1mm | 否 | 否 | F-u | ★★★★★ 最先做 |
| `Miehe2010_SENS_shear.jl`  | SENT 1×1mm | 否 | 否 | F-u（剪切） | ★★★★ |
| `Carrara2020_SENT_fatigue_Fig6.jl` | SENT 1×1mm | 否 | 是 | a-N | ★★★ |
| `Fang2019_flat_grooved_H01E.jl` | 平板18×50mm | 是 | 否 | F-u | ★★ |
| `Li_fig9_paperstyle.jl` | SENT 1×1mm | 是 | 是 | a-N | ★ 最后做 |

---

## GUI 需要有哪些功能

**最重要的一条原则：做出来的代码要让我好调试、好改。结构要清晰，不要过度封装。**

### 功能 1：参数输入面板

界面左侧要有一个面板，列出所有可以修改的参数，按类型分组。建议每组参数加一个折叠/展开的分组框（QGroupBox）：

**材料参数组：**
- 杨氏模量 E (MPa)，默认 210950
- 泊松比 ν，默认 0.3
- 屈服应力 σ_y0 (MPa)，默认 440（塑性算例才用，弹性算例灰掉）
- 硬化指数 n，默认 0.1（塑性算例才用）

**相场参数组：**
- 临界能量释放率 Gc (N/mm)，默认 2.7
- 裂纹长度尺度 l₀ (mm)，默认 0.015（这两个是最重要的相场参数）
- 疲劳阈值 αT，默认 11.25（疲劳算例才用）
- 数值稳定参数 η，默认 1e-10（一般不改，但要显示出来）

**加载参数组：**
- 最大位移 u_max (mm)，默认 0.008
- 粗加载步数 N_coarse，默认 500
- 粗步长 Δu_coarse (mm)，默认 8e-6
- 细步长 Δu_fine (mm)，默认 8e-6
- R 比（疲劳算例用），默认 0.0
- 循环总数 N_cycles（疲劳算例用），默认 800
- 每循环子步数（疲劳算例用），默认 20

**网格参数组：**
- 细网格尺寸 h_fine (mm)，默认 0.005
- 粗网格尺寸 h_coarse (mm)，默认 0.05
- 预裂纹长度 a₀ (mm)，默认 0.5
- 试样宽度 W (mm)，默认 1.0
- 试样高度 H (mm)，默认 1.0

### 功能 2：算例选择和网格选择

顶部有两个下拉菜单：
- **算例类型**：`弹性断裂-拉伸(SENT)` / `弹性断裂-剪切(SENS)` / `弹性疲劳` / `塑性断裂` / `弹塑性疲劳`
- **网格来源**：`自动生成（使用上方参数）` / `导入已有 .msh 文件`

选择"导入已有 .msh 文件"时，旁边出现一个"选择文件"按钮，让用户从磁盘选一个 `.msh` 文件。**选了自定义网格后，程序就直接用这个文件，不再调用 Gmsh 重新生成。**

### 功能 3：运行和停止

- 绿色"▶ Run"按钮：点击后启动 Julia 计算。点击后按钮变灰、Stop 按钮变红可用。
- 红色"■ Stop"按钮：点击后中止计算（通过写 `gui_stop.flag` 文件实现，详见后面）。停止后两个按钮状态恢复。

### 功能 4：损伤场云图（右上区域）

界面右侧上半部分显示损伤场 PNG 图片。Julia 每隔 N 步（默认每 50 步）保存一张 PNG，Python 收到 Julia 打印的 `SNAPSHOT 文件路径` 这一行后，立刻加载并刷新显示。

用 PyQt5 的 `QLabel + QPixmap` 即可，不需要复杂的图形库。

### 功能 5：曲线（右下区域）

右侧下半部分显示一张折线图（用 matplotlib 嵌入 PyQt5）。

- **弹性断裂 / 塑性断裂**：F-u 曲线，横轴施加位移（mm），纵轴反力（N）
- **弹性疲劳 / 弹塑性疲劳**：a-N 曲线，横轴循环数 N，纵轴裂纹长度 a（mm）

每收到一行 `STEP` 或 `CYCLE` 数据就追加一个点，调用 `canvas.draw_idle()` 重绘。

### 功能 6：进度条和日志

- 进度条：收到 `PROGRESS 45.2` 这行时更新到 45%
- 状态文字：显示当前步数、当前最大损伤值（d_max）、当前力
- 日志滚动窗口（QTextEdit）：显示 Julia 输出的最近 60 行，用等宽字体

### 功能 7：打开 ParaView（加分项）

一个按钮，点击后在后台运行 `paraview 最新的.vtu文件路径`。Julia 每次输出 VTK 文件后也在 `SNAPSHOT` 旁边写一行 `VTK 文件路径`，Python 记录最后一个 VTK 路径，点按钮时打开它。

---

## 用什么语言和框架写 GUI

**GUI 部分用 Python + PyQt5 写，Julia 作为后台计算子进程运行。**

具体通信流程：

```
用户填参数、点Run
    ↓
Python 把参数写成 params.json
    ↓
Python 启动子进程: julia gui_solver.jl params.json
    ↓
Julia 跑计算，每步把结果打到 stdout（一行一行）
    ↓
Python 实时读取 stdout，根据行前缀更新界面
    ↓
Julia 每 50 步保存一张 PNG 到磁盘，同时打印 "SNAPSHOT 路径"
    ↓
Python 收到 SNAPSHOT 行，加载 PNG，刷新云图显示区
```

这个方案的好处是 **Python 和 Julia 完全解耦**，两边都可以单独测试，不用一起跑。

Python GUI 框架用 **PyQt5**，安装：
```bash
pip install PyQt5 matplotlib
```

---

## Julia 侧的适配脚本：`gui_solver.jl`

你需要在 `gui/` 目录下新建一个文件 `gui_solver.jl`，这个文件做三件事：

### 第一件事：从 JSON 文件读取参数

```julia
using JSON3
p = JSON3.read(open(ARGS[1]), Dict{String,Any})
E  = p["E"]
Gc = p["Gc"]
l0 = p["l0"]
# ... 其他参数类似
```

运行方式：`julia gui_solver.jl params.json`

### 第二件事：向 stdout 打印固定格式的进度行（Python 解析这些）

```
INFO 网格生成完成，节点数 18432
STEP 50 U 4.00e-04 F 3.21e+02 DMAX 0.0032
STEP 51 U 4.08e-04 F 3.25e+02 DMAX 0.0035
PROGRESS 5.1
SNAPSHOT gui_results/snap_000050.png
CYCLE 100 A 0.523 DMAX 0.234        ← 疲劳算例用这个，不用 STEP
DONE
ERROR 报错信息
```

每一行的字段含义：
- `STEP n` — 第 n 步
- `U 4.00e-04` — 当前施加位移（mm）
- `F 3.21e+02` — 当前顶边反力（N）
- `DMAX 0.0032` — 当前损伤场最大值（0=完好，1=完全断裂）
- `PROGRESS 5.1` — 进度百分比
- `SNAPSHOT 路径` — 保存了一张 PNG，路径在后面
- `CYCLE n` — 疲劳算例用，第 n 个循环
- `A 0.523` — 疲劳算例用，当前裂纹长度（mm）

### 第三件事：每 N 步保存一张损伤场 PNG

现有脚本里已经有 `plot_scalar_field_heatmap()` 这样的函数。直接把它搬过来用，或者仿照着写，用 Plots.jl 的 `heatmap()` 生成热力图保存成 PNG。保存完后打印 `SNAPSHOT 路径` 这一行。

### 停止机制

Python 在 `gui/` 目录下创建一个空文件 `gui_stop.flag`，Julia 在每步的开头检查：

```julia
if isfile("gui_stop.flag")
    rm("gui_stop.flag"; force=true)
    println("INFO Stopped by user")
    flush(stdout)
    break
end
```

---

## Python GUI 的代码结构

建议把代码分成两个类，写在同一个文件 `gui_main.py` 里：

### 类 1：`JuliaWorker(QThread)`

在独立线程里运行 Julia 子进程，读取 stdout，解析每一行，通过 PyQt5 的信号（`pyqtSignal`）把数据发给主线程更新界面。**必须用 QThread，否则 Julia 跑起来时界面会冻住无法操作。**

```python
class JuliaWorker(QThread):
    sig_step     = pyqtSignal(int, float, float, float)  # n, u, F, d_max
    sig_cycle    = pyqtSignal(int, float, float)          # n, a, d_max
    sig_progress = pyqtSignal(float)                      # 百分比
    sig_snapshot = pyqtSignal(str)                        # PNG 路径
    sig_done     = pyqtSignal()
    sig_error    = pyqtSignal(str)

    def run(self):
        self.process = subprocess.Popen(
            ["julia", "gui_solver.jl", self.params_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(GUI_DIR)
        )
        for line in self.process.stdout:
            line = line.rstrip()
            # 根据行前缀发射对应的信号
            if line.startswith("STEP"):
                # 解析 n, u, F, d_max，然后 self.sig_step.emit(n, u, F, d)
                ...
            elif line.startswith("CYCLE"):
                ...
            elif line.startswith("SNAPSHOT"):
                path = line.split(None, 1)[1]
                self.sig_snapshot.emit(path)
            elif line.startswith("DONE"):
                self.sig_done.emit()
            elif line.startswith("ERROR"):
                self.sig_error.emit(line[6:])
```

### 类 2：`MainWindow(QMainWindow)`

主窗口，左侧参数面板 + 右侧可视化区。响应 JuliaWorker 发来的信号更新界面：

```python
# 收到损伤场快照时：
def _on_snapshot(self, path):
    pixmap = QPixmap(path)
    self.field_label.setPixmap(
        pixmap.scaled(self.field_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    )

# 收到 STEP 数据时，追加到曲线并重绘：
def _on_step(self, n, u, F, d):
    self.u_data.append(u)
    self.F_data.append(F)
    self.line_fu.set_data(self.u_data, self.F_data)
    self.ax.relim()
    self.ax.autoscale_view()
    self.canvas.draw_idle()
    self.lbl_status.setText(f"Step {n} | d_max={d:.4f} | F={F:.1f} N")
```

---

## 文件组织

建议这样组织，不要把 GUI 文件和原始仿真脚本混在一起：

```
/Users/zhangpeng/Desktop/PFM-paper/
├── code/                              ← 原始 Julia 仿真脚本（不要动！）
│   ├── Miehe2010_SENT_tension.jl      ← SENT 弹性断裂，优先从这里抄参数
│   ├── Miehe2010_SENS_shear.jl        ← SENS 剪切断裂
│   ├── Fang2019_flat_grooved_H01E.jl  ← 塑性断裂（几何不同，后做）
│   ├── Carrara2020_SENT_fatigue_Fig6.jl ← 弹性疲劳
│   └── Li_fig9_paperstyle.jl          ← 弹塑性疲劳（最后做）
└── gui/                               ← 所有 GUI 文件放这里
    ├── gui_main.py                    ← Python GUI 主程序（你来写）
    ├── gui_solver.jl                  ← Julia 适配脚本（你来写）
    ├── params_default.json            ← 默认参数（启动时自动加载）
    └── gui_results/                   ← Julia 运行时自动创建，存结果
        ├── mesh_SENT.msh
        ├── snap_000050.png
        ├── Fu_curve.csv
        └── result_000100.vtu
```

---

## 交付优先级

**第一步（必须做，最先交付）：**
把 `Miehe2010_SENT_tension.jl`（SENT 拉伸弹性断裂）跑通。能打开界面、修改 Gc 和 l₀、点 Run、看到损伤场云图随时间更新、看到 F-u 曲线实时延伸，就算第一步完成。

**第二步：**
加上 SENS 剪切算例，加上自定义网格导入功能。

**第三步：**
加上疲劳算例（`Carrara2020_SENT_fatigue_Fig6.jl`），界面上的 F-u 曲线改成 a-N 曲线。

**第四步（时间够的话）：**
加上塑性断裂（`Fang2019_flat_grooved_H01E.jl`）和弹塑性疲劳（`Li_fig9_paperstyle.jl`）。

---

## 调试建议（非常重要）

**调 Julia 侧的问题，永远先用命令行单独跑，不要通过 GUI 看：**

```bash
cd /Users/zhangpeng/Desktop/PFM-paper/gui
julia gui_solver.jl params_default.json
```

正常情况下你会在终端里看到：
```
INFO 网格生成完成：gui_results/mesh_SENT.msh
INFO 开始求解，预计约 1000 步
STEP 1 U 8.000000e-06 F 1.23e+02 DMAX 0.000001
STEP 2 U 1.600000e-05 F 2.46e+02 DMAX 0.000002
PROGRESS 0.2
...
SNAPSHOT gui_results/snap_000050.png
...
DONE
```

如果 Julia 报错，完整的错误栈会直接在终端里显示，比通过 GUI 日志窗口看清楚得多。

**调 Python 侧的问题，可以在 `JuliaWorker.run()` 的循环里临时加一行：**
```python
print(f"[RAW] {repr(line)}")   # 确认 Python 收到的 stdout 格式是否正确
```

**Julia 首次启动很慢（30–60 秒）是正常的，** 因为 Julia 需要预编译所有依赖包。第二次之后就只需要 5–10 秒。不用担心，不是 GUI 的问题。

---

*如有疑问直接来问我。*
