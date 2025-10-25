#!/bin/bash
# 프록시 서버 자동 설치 스크립트
# Ubuntu/Debian 전용

echo "=========================================="
echo "  쿠팡 크롤러용 Squid 프록시 자동 설치"
echo "=========================================="
echo ""

# 루트 권한 확인
if [ "$EUID" -ne 0 ]; then
    echo "❌ 이 스크립트는 root 권한이 필요합니다."
    echo "다음 명령으로 실행하세요: sudo bash install_proxy.sh"
    exit 1
fi

# 사용자 IP 입력
echo "📝 당신의 IP 주소를 입력하세요 (프록시 접근 허용용)"
echo "💡 IP 확인: https://www.whatismyip.com/"
read -p "IP 주소: " USER_IP

if [ -z "$USER_IP" ]; then
    echo "❌ IP 주소가 입력되지 않았습니다."
    exit 1
fi

# 포트 선택
read -p "프록시 포트 (기본: 3128): " PROXY_PORT
PROXY_PORT=${PROXY_PORT:-3128}

echo ""
echo "=========================================="
echo "설치 시작..."
echo "=========================================="

# 1. 시스템 업데이트
echo "📦 시스템 업데이트 중..."
apt update -qq

# 2. Squid 설치
echo "📦 Squid 프록시 설치 중..."
apt install -y squid

# 3. 설정 파일 백업
echo "💾 기존 설정 백업 중..."
cp /etc/squid/squid.conf /etc/squid/squid.conf.backup

# 4. 새 설정 파일 작성
echo "⚙️  설정 파일 생성 중..."
cat > /etc/squid/squid.conf << EOF
# Squid 프록시 설정 - 쿠팡 크롤러용
# 생성일: $(date)

# 포트 설정
http_port ${PROXY_PORT}

# 접근 제어 - 특정 IP만 허용
acl allowed_ips src ${USER_IP}/32
http_access allow allowed_ips

# 나머지 모두 차단
http_access deny all

# 로그 설정
access_log /var/log/squid/access.log squid
cache_log /var/log/squid/cache.log

# 캐시 설정 (선택사항)
cache_dir ufs /var/spool/squid 100 16 256

# 익명성 강화
forwarded_for off
via off

# 타임아웃 설정
connect_timeout 60 seconds
read_timeout 300 seconds

# DNS 설정
dns_nameservers 8.8.8.8 8.8.4.4
EOF

# 5. Squid 재시작
echo "🔄 Squid 재시작 중..."
systemctl restart squid
systemctl enable squid

# 6. 방화벽 설정 (UFW)
if command -v ufw &> /dev/null; then
    echo "🔥 UFW 방화벽 설정 중..."
    ufw allow ${PROXY_PORT}/tcp
    ufw --force enable
fi

# 7. iptables 설정
echo "🔥 iptables 방화벽 설정 중..."
iptables -I INPUT -p tcp --dport ${PROXY_PORT} -j ACCEPT

# iptables 영구 저장 시도
if command -v netfilter-persistent &> /dev/null; then
    netfilter-persistent save
elif command -v iptables-save &> /dev/null; then
    iptables-save > /etc/iptables/rules.v4
fi

# 8. 상태 확인
echo ""
echo "=========================================="
echo "✅ 설치 완료!"
echo "=========================================="
echo ""

# Squid 상태 확인
if systemctl is-active --quiet squid; then
    echo "✅ Squid 프록시 정상 작동 중"
else
    echo "❌ Squid 프록시 시작 실패"
    echo "로그 확인: sudo journalctl -u squid -n 50"
    exit 1
fi

# 서버 IP 가져오기
SERVER_IP=$(curl -s https://ipinfo.io/ip)

echo ""
echo "=========================================="
echo "📋 프록시 정보"
echo "=========================================="
echo "프록시 주소: http://${SERVER_IP}:${PROXY_PORT}"
echo "허용된 IP: ${USER_IP}"
echo "포트: ${PROXY_PORT}"
echo ""
echo "=========================================="
echo "🧪 테스트 방법"
echo "=========================================="
echo "로컬 컴퓨터에서 다음 명령으로 테스트:"
echo ""
echo "curl -x http://${SERVER_IP}:${PROXY_PORT} https://ipinfo.io/json"
echo ""
echo "결과에 ${SERVER_IP}가 나오면 성공!"
echo ""
echo "=========================================="
echo "🔧 관리 명령어"
echo "=========================================="
echo "상태 확인: sudo systemctl status squid"
echo "재시작: sudo systemctl restart squid"
echo "중지: sudo systemctl stop squid"
echo "로그 확인: sudo tail -f /var/log/squid/access.log"
echo "설정 파일: /etc/squid/squid.conf"
echo ""
echo "=========================================="
echo "📱 프로그램에서 사용"
echo "=========================================="
echo "1. 프로그램 실행: python3 10.coupang_wing.py"
echo "2. 설정 탭 → 프록시 사용 체크"
echo "3. 프록시 서버: http://${SERVER_IP}:${PROXY_PORT}"
echo "4. 설정 저장 클릭"
echo ""
echo "🎉 설치 완료! 즐거운 크롤링 되세요!"
