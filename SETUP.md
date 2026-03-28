## 启动条例
### 注意：请务必确保命令均在工作目录下运行
0. 确认机械臂断电，电脑已经接入机械臂 USB 、机械臂网线、摄像头、灵巧手。

1. 开启电脑，使用 usbipd bind 以上设备。 ```usbipd bind --busid <BUSID>```
2. 启动 WSL 使用 usbipd attach 以上设备。 ```usbipd attach --wsl --busid <BUSID>```
3. 进入工作目录，**请修改该路径为你的工作路径**。 ```cd /root/dev/MITHackathon-Teleoperation```
4. 在 WSL 终端中加载 Linux 内核并拉起服务。 
```
sudo modprobe can
sudo modprobe can_raw
sudo modprobe gs_usb
sudo modprobe uvcvideo
sudo modprobe cdc_acm
sudo bash pyAgxArm/pyAgxArm/scripts/ubuntu/can_activate.sh can0 1000000
sudo ip link set can0 up
```
5. 给机械臂通电，在上位机中打开 CAN 口通信。
6. 测试 ```candump can0``` ，确保有输出。
7. 检查 ```ip -details link show can0``` 。

正确输出如下：
```
6: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT group default qlen 10
    link/can  promiscuity 0 minmtu 0 maxmtu 0 
    can state ERROR-ACTIVE restart-ms 0 
          bitrate 1000000 sample-point 0.750 
          tq 62 prop-seg 5 phase-seg1 6 phase-seg2 4 sjw 2
          gs_usb: tseg1 1..16 tseg2 1..8 sjw 1..4 brp 1..1024 brp-inc 1
          clock 48000000 numtxqueues 1 numrxqueues 1 gso_max_size 65536 gso_max_segs 65535 parentbus usb parentdev 1-1:1.0 
```
8. 进行机械臂标定。确保深度相机和机械臂都处在最终固定位置。

采集标定数据：
```
python scripts/calibration/capture_eye_to_hand.py \
  --channel can0 \
  --board-type charuco \
  --board-cols 11 \
  --board-rows 8 \
  --square-size-mm 15 \
  --marker-size-mm 11 \
  --aruco-dict DICT_4X4_50 \
  --samples 15 \
  --output-dir data/calib_run_0328am5
```
计算标定文件：
```
python scripts/calibration/solve_eye_to_hand.py \
  --dataset-dir data/calib_run_0328am5 \
  --method park
 ```
 测试标定误差：
 ```
 python scripts/calibration/verify_eye_to_hand.py \
  --calibration-file data/calib_run_0328am5/calibration_result.yaml \
  --channel can0 \
  --camera-serial 241222074755 \
  --samples 5
 ```

9. 使用终端启动设备。
```
python scripts/control/run_fake_grasp_cycle.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file data/calib_run_0328am5/calibration_result.json \
  --imgsz 960 \
  --hover-height-m 0.20 \
  --grasp-z-offset-m 0.078 \
  --grasp-offset-m 0.12 0 0 \
  --grasp-rpy-deg 90.10 -30 -1.41 \
  --pose-rpy-deg 90.10 -30 -1.41 \
  --drop-hover-z-m 0.35 \
  --drop-z-m 0.25 \
  --drop-hover-offset-m 0.10 \
  --rotate-inference-modes none cw90 ccw90 \
  --go
 ```


 10. 确认运行正常后在两个终端中分别运行 WebUI 的前后端。推荐的启动顺序是先后端，再前端。
 
 后端：
 ```
 source "$(conda info --base)/etc/profile.d/conda.sh"
 conda activate grasp-gpu
 DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
 python scripts/control/web_console_api.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file /root/dev/MITHackathon-Teleoperation/data/calib_run_0328am5/calibration_result.yaml \
  --imgsz 960 \
  --rotate-inference-modes none cw90 ccw90 \
  --host 0.0.0.0 \
  --port 8000
 ```
 
 前端：
 ```
 cd /root/dev/MITHackathon-Teleoperation/webapp
 export VITE_USE_MOCK=false
 /home/robot/.local/node-v20.19.0-linux-x64/bin/npm run dev -- --host 0.0.0.0 --port 5173
 ```