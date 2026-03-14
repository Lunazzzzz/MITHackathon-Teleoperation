from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_demo_launch
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression

def generate_launch_description():
    moveit_config = MoveItConfigsBuilder("piper", package_name="piper_with_gripper_moveit").to_moveit_configs()
    ld = generate_demo_launch(moveit_config)

    ld.add_action(
        DeclareLaunchArgument(
            "joint_states",
            default_value="/joint_states",
            description="If not /joint_states, relay /joint_states to this topic (e.g. /control/joint_states).",
        )
    )
    ld.add_action(
        ExecuteProcess(
            condition=IfCondition(
                PythonExpression(
                    ["'", LaunchConfiguration("joint_states"), "' != '/joint_states'"]
                )
            ),
            cmd=[
                "ros2",
                "run",
                "topic_tools",
                "relay",
                "/joint_states",
                LaunchConfiguration("joint_states"),
            ],
            output="screen",
        )
    )

    return ld