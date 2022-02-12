from asyncio.constants import ACCEPT_RETRY_DELAY
from pickle import TRUE
from posixpath import isabs
from typing import Optional
from enum import Enum

import time

import rospy
import rosgraph
import rosnode
import rospkg

import yaml

from .utils import *
from .board import BoardType, determine_board, check_firmware_version
from leo_msgs.msg import Imu, WheelOdom, WheelStates
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32 

rospack = rospkg.RosPack()

###YAML PARSER

def parse_yaml(file_path):
    with open(file_path, "r") as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

    return {}

path = rospack.get_path('leo_fw')
motor_valid = parse_yaml(path+"/validate/motor.yaml")

imuData = Imu()
wheelData = WheelStates()
batteryData = Float32()

isNewImuData = 0
isNewWheelData = 0
isNewBatteryData = 0

isWheelLoaded = 0
wheelSpeedLimit = 0.05

class TestHW(Enum):
    HBRIDGE = "h_bridge"
    ENCODER = "encoder"
    TORQUE = "torque"
    IMU = "imu"
    BATTERY = "battery"
    ALL = "all"
    
    def __str__(self):
        return self.value

def batteryCallback(data):
    batteryData = data
    isNewBatteryData = 1

def imuCallback(data): 
    imuData = data
    isNewImuData = 1

def wheelCallback(data):
    wheelData = data
    isNewWheelData = 1

    #####################################################

###Publisher

cmd_vel_pub = rospy.Publisher('cmd_vel', Twist, queue_size=1)

cmd_pwmFL_pub = rospy.Publisher('firmware/wheel_FL/cmd_pwm_duty', Float32, queue_size=1)
cmd_pwmRL_pub = rospy.Publisher('firmware/wheel_RL/cmd_pwm_duty', Float32, queue_size=1)
cmd_pwmFR_pub = rospy.Publisher('firmware/wheel_FR/cmd_pwm_duty', Float32, queue_size=1)
cmd_pwmRR_pub = rospy.Publisher('firmware/wheel_RR/cmd_pwm_duty', Float32, queue_size=1)

###Subscriber

battery_sub = rospy.Subscriber('firmware/battery', Float32, batteryCallback)
wheel_sub = rospy.Subscriber('firmware/wheel_state', WheelStates, wheelCallback)
imu_sub = rospy.Subscriber('firmware/imu', Imu, imuCallback)

###WHEEL LOAD TEST

def check_motor_load():

    for x in range(1,20):

        cmd_pwmFL_pub.publish(Float32(x))
        cmd_pwmFR_pub.publish(Float32(x))
        cmd_pwmRL_pub.publish(Float32(x))
        cmd_pwmRR_pub.publish(Float32(x))

        rospy.sleep(0.1)

###MOTOR ENCODER TEST

def check_encoder():
    print(motor_valid)

###MOTOR TORQUE TEST

def check_torque():
    print(motor_valid)

###IMU TEST

def check_imu():
    msg_cnt = 0
    time_now = time.time()
    imu_valid = parse_yaml(path+"/validate/imu.yaml")

    accel_del = imu_valid["imu"]["accel_del"]
    accel_x = imu_valid["imu"]["accel_x"]
    accel_y = imu_valid["imu"]["accel_y"]
    accel_z = imu_valid["imu"]["accel_z"]

    gyro_del = imu_valid["imu"]["gyro_del"]
    gyro_x = imu_valid["imu"]["gyro_x"]
    gyro_y = imu_valid["imu"]["gyro_y"]
    gyro_z = imu_valid["imu"]["gyro_z"]

    while(msg_cnt<50):
        if (time_now+imu_valid["imu"]["timeout"] < time.time()):
            print("TIMEOUT")
            return 0

        if (isNewImuData == 1):
            time_now = time.time()
            isNewImuData = 0
            msg_cnt += 1

            if(accel_x-accel_del > imuData.accel_x > accel_x+accel_del or 
            accel_y-accel_del > imuData.accel_y > accel_y+accel_del or
            accel_z-accel_del > imuData.accel_z > accel_z+accel_del or
            gyro_x-gyro_del > imuData.gyro_x > gyro_x+gyro_del or
            gyro_y-gyro_del > imuData.gyro_y > gyro_y+gyro_del or
            gyro_z-gyro_del > imuData.gyro_z > gyro_z+gyro_del):
                print("INVALID DATA")
                return 0

    print("PASSED")
    return 1    

###BATTERY TEST

def check_battery(): 
    msg_cnt = 0
    time_now = time.time()
    batt_valid = parse_yaml(path+"/validate/battery.yaml") 

    while(msg_cnt<50):
        if (time_now+batt_valid["battery"]["timeout"] < time.time()):
            print("TIMEOUT")
            return 0

        if (isNewBatteryData == 1):
            time_now = time.time()
            isNewBatteryData = 0
            msg_cnt += 1

            if(batteryData.data <= batt_valid["battery"]["voltage_min"]):
                print("LOW VOLTAGE")
                return 0
            elif(batteryData.data >= batt_valid["battery"]["voltage_max"]):
                print("HIGH VOLTAGE")
                return 0

    print("PASSED")
    return 1

#####################################################

def validate_hw(
    hardware: Optional[TestHW] = TestHW.ALL,
    rosbag: bool = False,
):

    write_flush("--> Checking if ROS Master is online.. ")

    if rosgraph.is_master_online():
        print("YES")
        master_online = True
    else:
        print("NO")
        master_online = False
        print(
            "ROS Master is not running. "
            "Will not be able to validate hardware."
            "Try to restart leo.service or reboot system."
        )
        return

    #####################################################

    if master_online:
        write_flush("--> Checking if rosserial node is active.. ")

        if rospy.resolve_name("serial_node") in rosnode.get_node_names():
            print("YES")
            serial_node_active = True
        else:
            print("NO")
            serial_node_active = False
            print(
                "Rosserial node is not active. "
                "Will not be able to validate hardware."
                "Try to restart leo.service or reboot system."
            )
            return

    #####################################################

    if master_online and serial_node_active:
        write_flush("--> Trying to determine board type.. ")

        board_type = determine_board()

        if board_type is not None:
            print("SUCCESS")
        else:
            print("FAIL")


    #####################################################

    current_firmware_version = "<unknown>"

    if master_online and serial_node_active:
        write_flush("--> Trying to check the current firmware version.. ")

        current_firmware_version = check_firmware_version()

        if current_firmware_version != "<unknown>":
            print("SUCCESS")
        else:
            print("FAIL")

    #####################################################

    if current_firmware_version == "<unknown>" or board_type is None:
        print(
            "Can not determine firmware version or board type. "
            "Flash firmware and try to rerun the script"
        )
        return

    #####################################################

    if master_online and serial_node_active:
        write_flush("--> Initializing ROS node.. ")
        rospy.init_node("leo_core_validation", anonymous=True)
        print("DONE")

    #####################################################

    print(f"Firmware version: {current_firmware_version}")
    if board_type == BoardType.CORE2:
        print(f"Board type: Core2ROS")
    elif board_type == BoardType.LEOCORE:
        print(f"Board type: LeoCore")

    #####################################################

    if not query_yes_no("Run test?"):
        return

    #####################################################
    
    if (hardware==TestHW.ALL or hardware==TestHW.BATTERY):
        write_flush("--> Battery validation.. ")
        check_battery()
    
    if (hardware==TestHW.ALL or hardware==TestHW.IMU):
        write_flush("--> IMU validation.. ")
        check_imu()

    if (hardware==TestHW.ALL or hardware==TestHW.ENCODER): 
        write_flush("--> Encoders validation.. ")
        check_encoder()

    if (hardware==TestHW.ALL or hardware==TestHW.TORQUE):
        write_flush("--> Torque sensors validation.. ")
        check_torque()
  
    #####################################################

