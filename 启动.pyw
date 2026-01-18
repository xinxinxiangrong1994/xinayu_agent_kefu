# 无控制台启动（双击此文件启动程序）
import sys
from pathlib import Path

# 确保能找到模块
sys.path.insert(0, str(Path(__file__).parent))

from gui import XianyuGUI

if __name__ == "__main__":
    app = XianyuGUI()
    app.run()
