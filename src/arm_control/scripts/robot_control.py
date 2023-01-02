#!/usr/bin/python3

import rospy
import threading
import numpy as np

from Phidget22.Phidget import *
from Phidget22.Devices.VoltageOutput import *

from arm_msgs.msg import arm_robot_state
from arm_msgs.msg import arm_joint_state
from arm_msgs.msg import arm_dynamixel_state


### Global 변수
state_lock = threading.Lock()
robot_state = arm_robot_state()

def msg_sub_seperate_msgs(robot_state: arm_robot_state):
    def processing(data :arm_robot_state) -> None:
        state_lock.acquire()
        robot_state.input_command = data.input_command
        robot_state.L1 = data.L1
        robot_state.L2 = data.L2
        robot_state.L3 = data.L3
        robot_state.L4 = data.L4
        robot_state.L5 = data.L5
        robot_state.L6 = data.L6
        robot_state.L7 = data.L7
        robot_state.L8 = data.L8

        robot_state.R1 = data.R1
        robot_state.R2 = data.R2
        robot_state.R3 = data.R3
        robot_state.R4 = data.R4
        robot_state.R5 = data.R5
        robot_state.R6 = data.R6
        robot_state.R7 = data.R7
        robot_state.R8 = data.R8

        robot_state.DXL1 = data.DXL1
        robot_state.DXL2 = data.DXL2
        robot_state.DXL3 = data.DXL3
        robot_state.DXL4 = data.DXL4
        state_lock.release()

    rospy.Subscriber("robot_state", arm_robot_state, callback=processing)

def checking_state_msg(robot_state: arm_robot_state):
    import time
    rospy.loginfo("Checking state msg...")
    log_once = True
    checking_duration = rospy.Duration(secs=2)

    msg_check_rate = rospy.Rate(5)
    
    while not rospy.is_shutdown():
        t_start = rospy.Time.now()
        t_check = t_start

        t_input = t_start

        while not ((t_check - t_start).to_sec()) > checking_duration.to_sec():
            t_check = rospy.Time.now()

            state_lock.acquire()
            t_input = robot_state.input_command.header.stamp
            state_lock.release()

            time.sleep(0.25)

        if (t_input - t_start).to_sec() > 1.5:
            if log_once:
                rospy.loginfo("State msg chekcing done! This control node check state msg at 5Hz...")
                log_once = False
        else:
            rospy.logerr("State msg is wrong shutdown control node...")
            rospy.on_shutdown(cylinder_volate_output(robot_state))

        msg_check_rate.sleep()

def dynamixel_controller():
    import dynamixel_sdk

    """
    System Parameter Define
    """
    # Cormidi Lever Parameter
    _deg_min = [5,  5, -1, -1]
    _deg_max = [1009, 1009, 1, 1]

    _track_inf = [0,0]

    _lever_min = [500, 1160, 2310, 2297] 
    _lever_max = [1600, 2260, 2750, 2800]

    # Dynamixel Comm Paramters
    _PortName = ''
    _CommBaudrate = 115200
    _ProtocolVer = 1.0
    _DX_ID = [11,12,13,14]

    # Dynamixel Protocol Parameters
    _ADDR_MX_TORQUE_ENABLE = 24
    _ADDR_MX_GOAL_POSITION = 30
    _ADDR_MX_PRESENT_POSITION = 36

    _TORQUE_ENABLE = 1
    _TORQUE_DISABLE = 0

    _LEN_MX_GOAL_POSITION = 4
    _LEN_MX_PRESENT_POSITION = 4
    """
    System Parameter Define Done
    """

    """
    Inline Function
    """

    def mapping(value, i):
        if value > 1100 :       # Master의 Master의 트랙_L, 트랙_R 값은 deg_max가 1009이므로 1100이상의 쓰레기 값이 들어오면 Dynamixel을 중립 값으로 제어함
            return 1050 if i == 0 else 1738

        sampling = 20       # 계수, 20*deg_range개
        lev_Range = _lever_max[i] - _lever_min[i]
        deg_Range = _deg_max[i] - _deg_min[i]

        ## Master Encoder → Dyanmixel의 비트값으로 매핑
        if i == 0:
            bit = _lever_min[i] + lev_Range // deg_Range * (value - _deg_min[i])
            bit = _lever_min[i] + _lever_max[i] - bit
            _track_inf[0] = value
        elif i == 1:
            bit = _lever_min[i] + lev_Range // deg_Range * (value - _deg_min[i])
            _track_inf[1] = value
        ## Master Encoder → Dyanmixel의 비트값으로 매핑

        elif i == 2:        ## 리프터 > -1이면 리프터가 내려가고 > 1이면 리프터가 올라감
            if value == -1 : bit = _lever_min[i]
            elif value == 1 : bit = _lever_max[i]
            elif value == 0 : bit = 2472        ## 중립값

        elif i== 3:
            ## HPMS (Hydraulic Power Managemnet System)
            if _track_inf[0]<380 or _track_inf[0]>635 or _track_inf[1]<380 or _track_inf[1]>635:        # 트랙_L, 트랙_R의 유효한 움직임이 있을 때
                if value != -1:     ## Master의 출력이 -1(POWER : 0%)가 아닐 때는 항상 중립(출력 50%)을 유지함
                    bit = 2600
                    ##2630 ~ 3220
                else:       ## Master의 출력이 -1(POWER : 0%)일 때는 출력 0%를 유지함
                    bit = _lever_min[i]
            else:       # 트랙이 유효한 움직임이 없을 때 (in Dead_Zone)
                if value == 0:      ## 출력 50%
                    bit = 2600
                elif value == 1:       ## 출력 100%
                    bit = _lever_max[i]
                elif value == -1:       ## 출력 0%
                    bit = _lever_min[i]

        if bit > _lever_max[i] :     ## 쓰레기 값 방어 > Constraint
            bit = _lever_max[i]
        elif bit < _lever_min[i] :
            bit = _lever_min[i]

        return bit

    """
    Inline Function Done
    """

    _status = False

    _ph = dynamixel_sdk.PortHandler(_PortName)
    _ph.openPort()
    _ph.setBaudRate(_CommBaudrate)
    _pah = dynamixel_sdk.PacketHandler(_ProtocolVer)

    _groupWrite = dynamixel_sdk.GroupSyncWrite(_ph, _pah, _ADDR_MX_GOAL_POSITION, _LEN_MX_GOAL_POSITION)
    _groupRead = dynamixel_sdk.GroupSyncRead(_ph, _pah, _ADDR_MX_PRESENT_POSITION, _LEN_MX_PRESENT_POSITION)

    _motorDirection = [0,0,0,0]

    try:
        for id in _DX_ID:
            comm_result, dxl_error = _pah.write1ByteTxRx(_ph, id, _ADDR_MX_TORQUE_ENABLE, _TORQUE_ENABLE)
            if comm_result != dynamixel_sdk.COMM_SUCCESS:
                rospy.logwarn_once(f"Error occur during on enabling DXL ID : {id} = " + str(_pah.getTxRxResult(comm_result)))
            elif dxl_error != 0:
                rospy.logwarn_once(f"Error msg for DXL ID : {id} = " + str(_pah.getRxPacketError(dxl_error)))
        
    except Exception as e:
        rospy.logerr(e + f" | Comm. establishing fail ({_PortName})! check port number.")

    while not rospy.is_shutdown():
        try:
            _groupWrite.addParam()
            pass
        except KeyboardInterrupt as ke:
            rospy.logerr(ke+f" | Closing {_PortName}...")
            _ph.closePort()

def cylinder_volate_output(robot_state: arm_robot_state):
    ############## Phidget #####################   PD 제어기 게인값 튜닝
    dt = 15        ## △t 15mmsec
    error_pre = [0.0]*16     ## master - slave
    error_cur = np.array([0.0]*16)
    D_error = [0.0]*16       ## △error
    # volt = [0.0]*16
    volt = np.zeros(16)
    # KP = [0.1, 0.2, 0.2, 0.4, 0.3, 0.15, 0, 0]*2     # P Gain 7,8번은 스위치로 변경되었으므로 게인값 없음
    KP = np.array([1.2, 1.6, 1.6, 1.4, 1.3, 1.15, 1, 1]*2)     # P Gain 7,8번은 스위치로 변경되었으므로 게인값 없음
    KD = np.array([0.2, 0.3, 0.3, 0.45, 0.1, 0.1, 0, 0]*2)    # D Gain 7,8번은 스위치로 변경되었으므로 게인값 없음
    I  = np.array([0.0] * 16)

    voltageOutput = [VoltageOutput() for _ in range(16)]

    try:
        for i in range(4):
            voltageOutput[i].setDeviceSerialNumber(525068)     ## R1~R4
            voltageOutput[i].setChannel(i)
            voltageOutput[i].openWaitForAttachment(1000)       ## 연결을 1000ms까지 대기함
            voltageOutput[i+4].setDeviceSerialNumber(525324)       ## R5~R8
            voltageOutput[i+4].setChannel(i)
            voltageOutput[i+4].openWaitForAttachment(1000)
            voltageOutput[i+8].setDeviceSerialNumber(525285)       ## L1~L4
            voltageOutput[i+8].setChannel(i)
            voltageOutput[i+8].openWaitForAttachment(1000)
            voltageOutput[i+12].setDeviceSerialNumber(525266)      ## L5~L8
            voltageOutput[i+12].setChannel(i)
            voltageOutput[i+12].openWaitForAttachment(1000)
    except:
        rospy.logerr("Fail to initiate Phidget board... closing control node...")
        # rospy.on_shutdown(cylinder_volate_output)

    def pdLoop():

        state_lock.acquire()
        error_cur[0] = robot_state.R1.error
        error_cur[1] = robot_state.R2.error
        error_cur[2] = robot_state.R3.error
        error_cur[3] = robot_state.R4.error
        error_cur[4] = robot_state.R5.error
        error_cur[5] = robot_state.R6.error
        error_cur[6] = int(robot_state.input_command.R7)
        error_cur[7] = int(robot_state.input_command.R8)
        
        error_cur[8]  = robot_state.L1.error
        error_cur[9]  = robot_state.L2.error
        error_cur[10] = robot_state.L3.error
        error_cur[11] = robot_state.L4.error
        error_cur[12] = robot_state.L5.error
        error_cur[13] = robot_state.L6.error
        error_cur[14] = int(robot_state.input_command.L7)
        error_cur[15] = int(robot_state.input_command.L8)
        state_lock.release()

        for i in range(16):
            #D_error[i] = error_cur[i] - error_pre[i]
            volt[i] = float(KP[i] * error_cur[i]) * -1

            if i==4: volt[i] = -volt[i]
            if i==12: volt[i] = -volt[i]

            if volt[i] > 0.1:      ## 데드존 보상
                volt[i] += 1.25
            elif volt[i] < -0.1:
                volt[i] -= 1.25

            volt[i] = round(volt[i],2)

            # if error_cur[i] > 100 and i!=6 and i!=7 and i!=14 and i!=15:     ## 180이 넘는 쓰레기 값이 들어오면 전압 값을 0으로 줌
            #     for i in range(16):
            #         volt[i] = 0
            #     break

            if volt[i] > 10:       ## 쓰레기 값에 대한 constraint
                volt[i] = 10
            elif volt[i] < -10:
                volt[i] = -10

        state_lock.acquire()

        if robot_state.input_command.R7 == 1:      ## R7,R8, L7,L8 제어
            volt[6] = -10
        elif robot_state.input_command.R7 == 0:
            volt[6] = 0
        else:
            volt[6] = 10

        if robot_state.input_command.R8 == 1:      ## R7,R8, L7,L8 제어
            volt[7] = -10
        elif robot_state.input_command.R8 == 0:
            volt[7] = 0
        else:
            volt[7] = 10

        if robot_state.input_command.L7 == 1:      ## R7,R8, L7,L8 제어
            volt[14] = -10
        elif robot_state.input_command.L7 == 0:
            volt[14] = 0
        else:
            volt[14] = 10

        if robot_state.input_command.L8 == 1:      ## R7,R8, L7,L8 제어
            volt[15] = -10
        elif robot_state.input_command.L8 == 0:
            volt[15] = 0
        else:
            volt[15] = 10

        state_lock.release()

        if abs(volt[6]) == 10 and abs(volt[7]) == 10:     ## R7, R8 이 동시에 -1(1) 값을 갖는 것을 방지함
            volt[6] = 0
            volt[7] = 0
        if abs(volt[14]) == 10 and abs(volt[15]) == 10:
            volt[14] = 0
            volt[15] = 0


        state_lock.acquire()
        robot_state.R1.calculated_voltage = volt[0]
        robot_state.R2.calculated_voltage = volt[1]
        robot_state.R3.calculated_voltage = volt[2]
        robot_state.R4.calculated_voltage = volt[3]
        robot_state.R5.calculated_voltage = volt[4]
        robot_state.R6.calculated_voltage = volt[5]
        robot_state.R7.calculated_voltage = volt[6]
        robot_state.R8.calculated_voltage = volt[7]

        robot_state.L1.calculated_voltage = volt[8]
        robot_state.L2.calculated_voltage = volt[9]
        robot_state.L3.calculated_voltage = volt[10]
        robot_state.L4.calculated_voltage = volt[11]
        robot_state.L5.calculated_voltage = volt[12]
        robot_state.L6.calculated_voltage = volt[13]
        robot_state.L7.calculated_voltage = volt[14]
        robot_state.L8.calculated_voltage = volt[15]

        state_lock.release()

        for i in range(8):
            voltageOutput[i].setVoltage(volt[i])

        # voltageOutput[3].setVoltage(-3)


    control_rate = rospy.Rate(100)
    while not rospy.is_shutdown():
        try:
            pdLoop()

        except KeyboardInterrupt as ke:
            for i in range(16):
                voltageOutput[i].setVoltage(0.0)

        control_rate.sleep()

    rospy.logwarn(f"Recieved shutdown signal set voltage to 0 V...")
    for i in range(16):
        voltageOutput[i].setVoltage(0.0)
    rospy.logwarn(f"Setting voltage done. safely locked!")

def pub_control_state(robot_state: arm_robot_state):
    rospy.loginfo("Control state publishing thread is running...")
    pub_rate = rospy.Rate(100)
    robot_state_pub = rospy.Publisher("control_state", arm_robot_state, queue_size=10)

    while not rospy.is_shutdown():
        state_lock.acquire()
        robot_state.header.stamp = rospy.rostime.Time.now()
        robot_state_pub.publish(robot_state)
        state_lock.release()

        pub_rate.sleep()



if __name__ == '__main__':
    rospy.init_node('arm_control')
    rospy.loginfo("Armstrong robot controller node start...") 

    ### robot_state 구독 및 개별 제어 값 메시지 생성
    th_msg_sub_seperate_msgs = threading.Thread(target=msg_sub_seperate_msgs, args=(robot_state,))
    th_msg_sub_seperate_msgs.start()


    ### robot_state 검증 함수 실행
    th_checking_state_msg = threading.Thread(target=checking_state_msg, args=(robot_state,))
    th_checking_state_msg.start()

    ### 다이나믹셀 제어 노드 생성


    ### 유압 실린더 전압 제어 노드 생성
    th_cylinder_volate_output = threading.Thread(target=cylinder_volate_output, args=(robot_state,))
    th_cylinder_volate_output.start()


    ### Publishing Voltage
    th_pub_control_state = threading.Thread(target=pub_control_state, args=(robot_state,))
    th_pub_control_state.start()

    rospy.spin()