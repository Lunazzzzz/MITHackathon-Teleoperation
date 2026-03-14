from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_moveit_rviz_launch


def generate_launch_description():
    moveit_config = MoveItConfigsBuilder("piper_h_description", package_name="piper_h_no_effector_moveit").to_moveit_configs()
    return generate_moveit_rviz_launch(moveit_config)
