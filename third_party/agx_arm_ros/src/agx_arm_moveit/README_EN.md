# agx_arm_moveit

[中文](./README.md)

|ROS |STATE|
|---|---|
|![humble](https://img.shields.io/badge/ros-humble-blue.svg)|![Pass](https://img.shields.io/badge/Pass-blue.svg)|
|![jazzy](https://img.shields.io/badge/ros-jazzy-blue.svg)|![Pass](https://img.shields.io/badge/Pass-blue.svg)|

> **Note:** For installation issues, refer to [Section 4](#4-troubleshooting).

---

## 1. Install MoveIt 2

1) Binary Installation
[Reference](https://moveit.ai/install-moveit2/binary/)

```bash
sudo apt install ros-$ROS_DISTRO-moveit*
```

2) Build from Source
[Reference](https://moveit.ai/install-moveit2/source/)

---

## 2. Install Dependencies

After installing MoveIt 2, additional dependencies are required:

```bash
sudo apt-get install -y \
    ros-$ROS_DISTRO-control* \
    ros-$ROS_DISTRO-joint-trajectory-controller \
    ros-$ROS_DISTRO-joint-state-* \
    ros-$ROS_DISTRO-gripper-controllers \
    ros-$ROS_DISTRO-trajectory-msgs
```

**Locale Configuration:** If your system locale is not set to English, configure as follows:

```bash
echo "export LC_NUMERIC=en_US.UTF-8" >> ~/.bashrc
source ~/.bashrc
```

---

## 3. Control Real Robot Arm with MoveIt 2

### 3.1 Launch agx_arm_ctrl

Before starting MoveIt 2, initialize the robot arm control node. See: [agx_arm_ctrl](../../README_EN.md)

### 3.2 MoveIt 2 Control

Open an additional terminal and run the following commands:

```bash
cd ~/catkin_ws
source install/setup.bash
```

#### 3.2.1 Without End Effector

1. Nero Robotic Arm 

    ```bash
    ros2 launch nero_no_effector_moveit demo.launch.py joint_states:=/control/joint_states
    ```

2. Piper Robotic Arm 

    ```bash
    ros2 launch piper_no_effector_moveit demo.launch.py joint_states:=/control/joint_states
    ```

3. Piper_X Robotic Arm 

    ```bash
    ros2 launch piper_x_no_effector_moveit demo.launch.py joint_states:=/control/joint_states
    ```

4. Piper_H Robotic Arm 

    ```bash
    ros2 launch piper_h_no_effector_moveit demo.launch.py joint_states:=/control/joint_states
    ```

5. Piper_L Robotic Arm 

    ```bash
    ros2 launch piper_l_no_effector_moveit demo.launch.py joint_states:=/control/joint_states
    ```

#### 3.2.2 With Gripper

1. Piper Robotic Arm 

    ```bash
    ros2 launch piper_with_gripper_moveit demo.launch.py joint_states:=/control/joint_states
    ```

2. Piper_X Robotic Arm 

    ```bash
    ros2 launch piper_x_with_gripper_moveit demo.launch.py joint_states:=/control/joint_states
    ```

![piper_moveit](./asserts/pictures/piper_moveit.png)

Drag the arrows at the arm's end-effector to manipulate the robot interactively.

Once the desired pose is set, click Plan & Execute under MotionPlanning → Planning in the left panel to generate and execute the trajectory.

## 4. Troubleshooting

### 4.1 Error Running `demo.launch.py`

**Error:** Parameter expects a double but received a string.

**Solution:**

**Option A:** Configure locale permanently
```bash
echo "export LC_NUMERIC=en_US.UTF-8" >> ~/.bashrc
source ~/.bashrc
```

**Option B:** Prefix launch command
```bash
LC_NUMERIC=en_US.UTF-8 ros2 launch piper_moveit_config demo.launch.py
```