from ament_index_python.packages import get_package_share_path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, LaunchConfiguration

from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

ROBOT_URDF_MAP = {
    'piper': 'piper/urdf/piper_description.urdf',
    'piper_x': 'piper_x/urdf/piper_x_description.urdf',
    'piper_l': 'piper_l/urdf/piper_l_description.urdf',
    'piper_h': 'piper_h/urdf/piper_h_description.urdf',
    'nero': 'nero/urdf/nero_description.urdf',
}

def resolve_model_path(context, *args, **kwargs):
    arm_type = LaunchConfiguration('arm_type').perform(context)
    pkg_path = get_package_share_path('agx_arm_description')

    if arm_type in ROBOT_URDF_MAP:
        model_path = str(pkg_path / 'agx_arm_urdf' / ROBOT_URDF_MAP[arm_type])
    else:
        urdf_dir = pkg_path / 'agx_arm_urdf'
        candidate = urdf_dir / arm_type
        if candidate.exists() and candidate.is_file():
            model_path = str(candidate)
        else:
            model_path = arm_type

    robot_description = ParameterValue(Command(['xacro ', model_path]), value_type=str)

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': robot_description}],
        remappings=[
            ('/joint_states', 'feedback/joint_states')
        ]
    )

    joint_state_publisher_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', LaunchConfiguration('rvizconfig')],
    )

    return [
        joint_state_publisher_node,
        robot_state_publisher_node,
        rviz_node,
    ]

def generate_launch_description():
    pkg_path = get_package_share_path('agx_arm_description')
    default_rviz_config_path = pkg_path / 'rviz/display.rviz'

    arm_type_arg = DeclareLaunchArgument(
        name='arm_type', default_value='piper',
        description='Robot arm type (e.g. piper, piper_x, piper_l, piper_h, nero) or a relative path under agx_arm_urdf/')
    rviz_arg = DeclareLaunchArgument(name='rvizconfig', default_value=str(default_rviz_config_path),
                                     description='Absolute path to rviz config file')

    return LaunchDescription([
        arm_type_arg,
        rviz_arg,
        OpaqueFunction(function=resolve_model_path),
    ])
