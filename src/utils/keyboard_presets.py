BYTE_A = ["0","9","8","7","6","5","4","3"]        # ACC(누산기)
BYTE_B = ["p","o","i","u","y","t","r","e"]        # IR(명령 레지스터)


SRC1 = ["Q","W","E","R","T","Y","U","I"]   # 피연산자1 (8비트)
SRC2 = ["A","S","D","F","G","H","J","K"]   # 피연산자2 (8비트)
RES  = ["Z","X","C","V","B","N","M",","]   # 연산 결과 (8비트)
SRC1_VALUE = "Tab"
SRC2_VALUE = "Caps Lock"
RES_VALUE = "Left Shift"

# PC(이번에 읽을 명령어 위치) 4비트
# IR(현재 명령어) 8비트

# Fetch = PC로부터 이번 명령어 IR에 가져오기
# Decode = 가져온 명령어(이미 기계어)를 실제 해야 하는 동작으로 변환
# Execute = 실제로 해당 동작을 ALU(산술논리연산기) 등이 계산 
# Write Back = 연산 결과를 레지스터나 메모리에 저장