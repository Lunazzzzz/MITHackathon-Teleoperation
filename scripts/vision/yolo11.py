import pyrealsense2 as rs
import numpy as np
import cv2
import torch.cuda
from ultralytics import YOLOWorld, YOLOE

# 1. 初始化 RealSense
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
print(torch.cuda.is_available())

profile = pipeline.start(config)

# 获取相机内参（用于 2D 转 3D）
intrinsics = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()

# 创建对齐对象 (将深度图对齐到彩色图)
align = rs.align(rs.stream.color)

# 2. 初始化 YOLO-World
model = YOLOE('yoloe-11s-seg.pt')
model.set_classes(["bottle", "cup", "screwdriver", "smartphone", "scissors"])

try:
    while True:
        # 获取帧并对齐
        frames = pipeline.wait_for_frames()
        aligned_frames = align.process(frames)

        color_frame = aligned_frames.get_color_frame()
        depth_frame = aligned_frames.get_depth_frame()

        if not color_frame or not depth_frame:
            continue

        # 转为 numpy 数组
        color_image = np.asanyarray(color_frame.get_data())

        # 3. YOLO 推理
        results = model.predict(source=color_image, conf=0.5, show=False)

        for r in results:
            for box in r.boxes:
                # 获取 Bounding Box 坐标
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                u, v = int((x1 + x2) / 2), int((y1 + y2) / 2)  # 中心像素点

                # 获取中心点深度
                dist = depth_frame.get_distance(u, v)

                # 如果中心点是黑洞 (0)，尝试在周围采样
                if dist == 0:
                    # 简单采样策略：取周围 5 像素范围内的有效深度
                    for i in range(-2, 3):
                        for j in range(-2, 3):
                            temp_dist = depth_frame.get_distance(u + i, v + j)
                            if temp_dist > 0:
                                dist = temp_dist
                                break

                if dist > 0:
                    # 4. 关键步骤：2D 像素坐标转 3D 空间坐标 (单位：米)
                    # result[0] 是 X (左右), result[1] 是 Y (上下), result[2] 是 Z (距离)
                    camera_coords = rs.rs2_deproject_pixel_to_point(intrinsics, [u, v], dist)

                    label = model.names[int(box.cls[0])]
                    print(f"物体: {label}")
                    print(
                        f" - 相机坐标系 X,Y,Z: {camera_coords[0]:.3f}, {camera_coords[1]:.3f}, {camera_coords[2]:.3f} 米")

                    # 5. 可视化：在图上标出距离
                    cv2.putText(color_image, f"{dist:.2f}m", (u, v),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # 显示画面
        cv2.imshow('YOLO-World + RealSense 3D', color_image)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    pipeline.stop()
    cv2.destroyAllWindows()