#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
프록시 매니저 - 여러 프록시를 관리하고 순환 사용
"""

import json
import random
from datetime import datetime, timedelta


class ProxyManager:
    def __init__(self, proxy_list_file='proxy_list.json'):
        self.proxy_list_file = proxy_list_file
        self.proxies = []
        self.current_index = 0
        self.load_proxies()

    def load_proxies(self):
        """프록시 목록 로드"""
        try:
            with open(self.proxy_list_file, 'r') as f:
                data = json.load(f)
                self.proxies = data.get('proxies', [])
        except FileNotFoundError:
            # 기본 프록시 목록 생성
            self.proxies = []
            self.save_proxies()

    def save_proxies(self):
        """프록시 목록 저장"""
        with open(self.proxy_list_file, 'w') as f:
            json.dump({
                'proxies': self.proxies,
                'last_updated': datetime.now().isoformat()
            }, f, indent=2)

    def add_proxy(self, proxy_url, name=''):
        """프록시 추가"""
        proxy_info = {
            'url': proxy_url,
            'name': name or proxy_url,
            'active': True,
            'success_count': 0,
            'fail_count': 0,
            'last_used': None,
            'added_at': datetime.now().isoformat()
        }
        self.proxies.append(proxy_info)
        self.save_proxies()
        print(f"프록시 추가됨: {proxy_url}")

    def remove_proxy(self, proxy_url):
        """프록시 제거"""
        self.proxies = [p for p in self.proxies if p['url'] != proxy_url]
        self.save_proxies()
        print(f"프록시 제거됨: {proxy_url}")

    def get_next_proxy(self):
        """다음 프록시 가져오기 (순환)"""
        if not self.proxies:
            return None

        # 활성 프록시만 필터링
        active_proxies = [p for p in self.proxies if p['active']]

        if not active_proxies:
            return None

        # 순환
        proxy = active_proxies[self.current_index % len(active_proxies)]
        self.current_index += 1

        # 사용 시간 업데이트
        for p in self.proxies:
            if p['url'] == proxy['url']:
                p['last_used'] = datetime.now().isoformat()
                break

        self.save_proxies()
        return proxy['url']

    def get_random_proxy(self):
        """랜덤 프록시 가져오기"""
        active_proxies = [p for p in self.proxies if p['active']]

        if not active_proxies:
            return None

        proxy = random.choice(active_proxies)

        # 사용 시간 업데이트
        for p in self.proxies:
            if p['url'] == proxy['url']:
                p['last_used'] = datetime.now().isoformat()
                break

        self.save_proxies()
        return proxy['url']

    def get_best_proxy(self):
        """성공률이 가장 높은 프록시 가져오기"""
        active_proxies = [p for p in self.proxies if p['active']]

        if not active_proxies:
            return None

        # 성공률 계산
        for p in active_proxies:
            total = p['success_count'] + p['fail_count']
            p['success_rate'] = p['success_count'] / total if total > 0 else 0

        # 성공률 순으로 정렬
        sorted_proxies = sorted(active_proxies, key=lambda x: x['success_rate'], reverse=True)
        proxy = sorted_proxies[0]

        # 사용 시간 업데이트
        for p in self.proxies:
            if p['url'] == proxy['url']:
                p['last_used'] = datetime.now().isoformat()
                break

        self.save_proxies()
        return proxy['url']

    def mark_success(self, proxy_url):
        """프록시 사용 성공 기록"""
        for p in self.proxies:
            if p['url'] == proxy_url:
                p['success_count'] += 1
                break
        self.save_proxies()

    def mark_failure(self, proxy_url):
        """프록시 사용 실패 기록"""
        for p in self.proxies:
            if p['url'] == proxy_url:
                p['fail_count'] += 1
                # 실패가 5번 이상이면 비활성화
                if p['fail_count'] >= 5:
                    p['active'] = False
                    print(f"프록시 비활성화됨 (실패 {p['fail_count']}회): {proxy_url}")
                break
        self.save_proxies()

    def list_proxies(self):
        """프록시 목록 출력"""
        print("\n=== 프록시 목록 ===")
        for i, p in enumerate(self.proxies, 1):
            status = "✅" if p['active'] else "❌"
            total = p['success_count'] + p['fail_count']
            success_rate = (p['success_count'] / total * 100) if total > 0 else 0

            print(f"{i}. {status} {p['name']}")
            print(f"   URL: {p['url']}")
            print(f"   성공률: {success_rate:.1f}% (성공: {p['success_count']}, 실패: {p['fail_count']})")
            print(f"   마지막 사용: {p['last_used'] or '사용 안 함'}")
            print()


# 사용 예시
if __name__ == '__main__':
    manager = ProxyManager()

    # 프록시 추가
    manager.add_proxy('http://123.45.67.89:3128', '서버1 (Squid)')
    manager.add_proxy('http://98.76.54.32:8888', '서버2 (TinyProxy)')
    manager.add_proxy('socks5://11.22.33.44:1080', '서버3 (SSH Tunnel)')

    # 프록시 목록 확인
    manager.list_proxies()

    # 다음 프록시 가져오기
    print("다음 프록시:", manager.get_next_proxy())
    print("다음 프록시:", manager.get_next_proxy())

    # 랜덤 프록시 가져오기
    print("랜덤 프록시:", manager.get_random_proxy())

    # 최고 성공률 프록시
    print("최고 프록시:", manager.get_best_proxy())

    # 성공/실패 기록
    manager.mark_success('http://123.45.67.89:3128')
    manager.mark_failure('http://98.76.54.32:8888')
