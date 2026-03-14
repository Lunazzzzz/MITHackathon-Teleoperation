import sys
sys.path.insert(0, "/root/sort_trash/scripts")

from omnihand_actions import create_actions

hand = create_actions("/root/sort_trash/config/sort_trash_pipeline.example.yaml")
import sys
import select
import tty
import termios
import time

def main():
    # 保存原始终端设置
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())  # 设置为 cbreak 模式，输入立即生效

    output_close = True   # True 输出 "Yes", False 输出 "No"

    try:
        while True:
            # 检查是否有输入可用（超时 0.1 秒）
            if select.select([sys.stdin], [], [], 0.1)[0]:
                key = sys.stdin.read(1)  # 读取一个字符
                if key == 'o':
                    output_close = False
                elif key == 'c':
                    output_close = True
                # 忽略其他按键

            # 输出当前状态
            if output_close:
                hand.close_hand()
            else:
                hand.open_hand()
            time.sleep(0.1)  # 控制输出频率

    except KeyboardInterrupt:
        print("\n程序已退出")
    finally:
        # 恢复终端设置
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

if __name__ == "__main__":
    main()