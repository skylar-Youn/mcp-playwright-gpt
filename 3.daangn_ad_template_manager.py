"""
당근마켓 광고 템플릿 관리 시스템
- 템플릿 추가/삭제/조회/생성
- 키워드나 링크 입력으로 광고 카피 생성
- 링크로 템플릿 자동 생성 (수동 입력)
- 클립보드 복사 기능
"""

import json
import os
import pyperclip
from datetime import datetime

TEMPLATE_FILE = "daangn_ad_templates.json"

# 기본 템플릿 구조
DEFAULT_TEMPLATES = {
    "이사": {
        "category": "이사/용달",
        "keywords": ["이사", "용달", "포장이사", "원룸이사", "투룸이사"],
        "title_templates": [
            "🚚 {지역} 알뜰이사 정직한 비용!",
            "💸 추가비용 NO! 안심이사",
            "📦 무료견적 | 이사전문",
            "✨ {지역} 이사 최저가 보장",
            "🏠 신뢰할 수 있는 이사서비스"
        ],
        "body_template": """🚚 이사 당일 추가요금 걱정 없어요!
❌ 견적 요청 버튼만 누르시면 견적을 받을 수 없습니다.
👉 꼭 아래 링크를 통해 요청해 주세요^^

📞 자세한 문의는 아래 링크로 주세요!
➡️ {link}

📦 정확한 이사비용, 무료 방문견적으로 확인!
☎️ 전화나 인터넷만으로는 정확한 이사비용을 알기 어렵습니다.
이사방에서는 무료 방문견적 서비스를 통해 현장에서 정확하게 확인 가능합니다.

📍 지역별 우수지점 2곳만 비교하여, 과도한 연락로 인한 피로를 덜어드립니다.

💸 추가요금 걱정 NO!
계약 시 안내된 이사비용 그대로 진행되며, 추가요금은 절대 발생하지 않습니다.

🛡️ 파손·분실 걱정 해결!
7일 이내 합의 및 보상방안을 마련해드리며, 고객 불편을 최우선으로 해결합니다.""",
        "cta": ["링크로 문의", "전화 문의", "채팅 상담"]
    }
}


class DaangnAdTemplateManager:
    def __init__(self):
        self.templates = self.load_templates()

    def load_templates(self):
        """템플릿 파일 로드"""
        if os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            self.save_templates(DEFAULT_TEMPLATES)
            return DEFAULT_TEMPLATES

    def save_templates(self, templates=None):
        """템플릿 저장"""
        if templates is None:
            templates = self.templates
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)

    def list_templates(self):
        """모든 템플릿 조회"""
        print("\n=== 저장된 광고 템플릿 목록 ===")
        if not self.templates:
            print("저장된 템플릿이 없습니다.")
            return []

        template_list = []
        for idx, (name, template) in enumerate(self.templates.items(), 1):
            print(f"\n{idx}. [{name}]")
            print(f"   카테고리: {template.get('category', 'N/A')}")
            print(f"   키워드: {', '.join(template.get('keywords', []))}")
            print(f"   제목 템플릿 수: {len(template.get('title_templates', []))}")
            template_list.append(name)

        return template_list

    def select_template_by_number(self):
        """번호로 템플릿 선택"""
        template_list = self.list_templates()
        if not template_list:
            return None

        choice = input("\n템플릿 번호 또는 이름 입력: ").strip()

        # 숫자인 경우
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(template_list):
                return template_list[idx]
            else:
                print("❌ 잘못된 번호입니다.")
                return None
        # 이름인 경우
        else:
            if choice in self.templates:
                return choice
            else:
                print(f"❌ 템플릿 '{choice}'을 찾을 수 없습니다.")
                return None

    def add_template(self, name, category, keywords, title_templates, body_template, cta):
        """새 템플릿 추가"""
        self.templates[name] = {
            "category": category,
            "keywords": keywords,
            "title_templates": title_templates,
            "body_template": body_template,
            "cta": cta,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save_templates()
        print(f"✅ 템플릿 '{name}' 추가 완료!")

    def delete_template(self, name):
        """템플릿 삭제"""
        if name in self.templates:
            del self.templates[name]
            self.save_templates()
            print(f"✅ 템플릿 '{name}' 삭제 완료!")
        else:
            print(f"❌ 템플릿 '{name}'을 찾을 수 없습니다.")

    def edit_template(self, name):
        """템플릿 수정"""
        template = self.get_template(name)
        if not template:
            print(f"❌ 템플릿 '{name}'을 찾을 수 없습니다.")
            return

        print(f"\n=== 템플릿 '{name}' 수정 ===")
        print("(수정하지 않으려면 엔터를 누르세요)")

        # 카테고리 수정
        print(f"\n현재 카테고리: {template.get('category', 'N/A')}")
        new_category = input("새 카테고리: ").strip()
        if new_category:
            template['category'] = new_category

        # 키워드 수정
        print(f"\n현재 키워드: {', '.join(template.get('keywords', []))}")
        new_keywords = input("새 키워드 (쉼표로 구분): ").strip()
        if new_keywords:
            template['keywords'] = [k.strip() for k in new_keywords.split(",")]

        # 제목 수정
        print(f"\n현재 제목 {len(template.get('title_templates', []))}개:")
        for idx, title in enumerate(template.get('title_templates', []), 1):
            print(f"  {idx}. {title}")

        edit_titles = input("\n제목을 수정하시겠습니까? (y/n): ").strip().lower()
        if edit_titles == 'y':
            print("새 제목 5개를 입력하세요:")
            new_titles = []
            for i in range(5):
                title = input(f"  제목 {i+1}: ").strip()
                if title:
                    new_titles.append(title)
            if new_titles:
                template['title_templates'] = new_titles

        # 본문 수정
        print(f"\n현재 본문 (길이: {len(template.get('body_template', ''))}자):")
        print(template.get('body_template', '')[:200] + "..." if len(template.get('body_template', '')) > 200 else template.get('body_template', ''))

        edit_body = input("\n본문을 수정하시겠습니까? (y/n): ").strip().lower()
        if edit_body == 'y':
            print("새 본문을 입력하세요 (엔터 2번으로 종료):")
            body_lines = []
            empty_count = 0
            while True:
                line = input()
                if line == "":
                    empty_count += 1
                    if empty_count >= 2:
                        break
                    body_lines.append(line)
                else:
                    empty_count = 0
                    body_lines.append(line)
            new_body = "\n".join(body_lines).strip()
            if new_body:
                template['body_template'] = new_body

        # CTA 수정
        print(f"\n현재 CTA: {', '.join(template.get('cta', []))}")
        new_cta = input("새 CTA (쉼표로 구분): ").strip()
        if new_cta:
            template['cta'] = [c.strip() for c in new_cta.split(",")]

        # 저장
        self.templates[name] = template
        template['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_templates()
        print(f"\n✅ 템플릿 '{name}' 수정 완료!")

    def get_template(self, name):
        """특정 템플릿 조회"""
        return self.templates.get(name)

    def generate_ad(self, template_name, link="", region=""):
        """템플릿으로 광고 생성"""
        template = self.get_template(template_name)
        if not template:
            print(f"❌ 템플릿 '{template_name}'을 찾을 수 없습니다.")
            return None

        print("\n" + "="*80)
        print(f"📢 {template_name} 광고 카피")
        print("="*80)

        # 제목 5개 생성
        titles = []
        print("\n[제목 후보 5개]")
        for idx, title_tmpl in enumerate(template['title_templates'][:5], 1):
            title = title_tmpl.replace("{지역}", region if region else "우리동네")
            titles.append(title)
            print(f"{idx}. {title}")

        # 본문 생성
        print("\n[본문 광고]")
        body = template['body_template'].replace("{link}", link if link else "https://example.com")
        body = body.replace("{지역}", region if region else "우리동네")
        print(body)

        print("\n" + "="*80)

        # 전체 광고 텍스트 반환 (복사용)
        full_ad = "[제목 후보 5개]\n"
        for idx, title in enumerate(titles, 1):
            full_ad += f"{idx}. {title}\n"
        full_ad += f"\n[본문 광고]\n{body}"

        return full_ad

    def create_template_from_link(self, url_or_keyword, category=""):
        """링크/키워드로 템플릿 생성 안내"""
        print(f"\n📝 '{url_or_keyword}'에 대한 템플릿 생성")
        print("\n" + "="*80)
        print("GPT 창 (ChatGPT/Claude 등)에 아래 프롬프트를 복사해서 붙여넣으세요:")
        print("="*80)

        prompt = f"""당신은 당근마켓 광고 카피라이터입니다.
아래 정보를 바탕으로 당근마켓 광고를 작성해주세요.

입력 정보: {url_or_keyword}
카테고리: {category if category else '자동 판단'}

요구사항:
1. 광고 제목 5개 (짧고 임팩트, 신뢰감+혜택 강조, 이모지 사용, 20자 이내)
2. 본문 광고 (이모지 활용, 짧은 문단, CTA 포함, 불안 해소, {{{{link}}}}, {{{{지역}}}} 변수 사용)

출력 형식:
---
템플릿 이름: [이름]
카테고리: [카테고리]
키워드: [키워드1, 키워드2, 키워드3]

[제목 5개]
1. 제목1
2. 제목2
3. 제목3
4. 제목4
5. 제목5

[본문]
본문 내용...
---"""

        print(prompt)
        print("\n" + "="*80)

        try:
            pyperclip.copy(prompt)
            print("✅ 프롬프트가 클립보드에 복사되었습니다!")
            print("👉 GPT 창에 붙여넣고 결과를 받아오세요.\n")
        except:
            print("⚠️ 위 프롬프트를 수동으로 복사하세요.\n")

        return None

    def interactive_add_template(self):
        """대화형 템플릿 추가 (수동 입력)"""
        print("\n=== 새 템플릿 추가 ===")
        name = input("템플릿 이름: ")
        category = input("카테고리 (예: 이사/용달, 부동산, 과외): ")
        keywords_input = input("키워드 (쉼표로 구분): ")
        keywords = [k.strip() for k in keywords_input.split(",")]

        print("\n제목 템플릿 5개를 입력하세요 ({지역}, {키워드} 등 변수 사용 가능):")
        title_templates = []
        for i in range(5):
            title = input(f"  제목 {i+1}: ")
            title_templates.append(title)

        print("\n본문 템플릿을 입력하세요 (엔터 2번으로 종료, {link}, {지역} 변수 사용 가능):")
        body_lines = []
        empty_count = 0
        while True:
            line = input()
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
                body_lines.append(line)
            else:
                empty_count = 0
                body_lines.append(line)
        body_template = "\n".join(body_lines).strip()

        cta_input = input("\nCTA 문구들 (쉼표로 구분, 예: 링크로 문의, 전화 문의): ")
        cta = [c.strip() for c in cta_input.split(",")]

        self.add_template(name, category, keywords, title_templates, body_template, cta)

    def parse_gpt_output(self, text):
        """GPT 출력 텍스트 파싱"""
        lines = text.strip().split('\n')

        name = ""
        category = ""
        keywords = []
        titles = []
        body_lines = []

        section = None

        for line in lines:
            line = line.strip()

            # 템플릿 이름
            if line.startswith("템플릿 이름:") or line.startswith("템플릿이름:"):
                name = line.split(":", 1)[1].strip()

            # 카테고리
            elif line.startswith("카테고리:"):
                category = line.split(":", 1)[1].strip()

            # 키워드
            elif line.startswith("키워드:"):
                kw_text = line.split(":", 1)[1].strip()
                # [키워드1, 키워드2] 형식 처리
                kw_text = kw_text.replace('[', '').replace(']', '')
                keywords = [k.strip() for k in kw_text.split(",")]

            # 섹션 구분
            elif line.startswith("[제목") or line.startswith("# 제목"):
                section = "titles"
            elif line.startswith("[본문") or line.startswith("# 본문"):
                section = "body"

            # 빈 줄이나 구분선 무시
            elif not line or line.startswith("---") or line.startswith("==="):
                continue

            # 제목 섹션
            elif section == "titles":
                # 숫자로 시작하는 줄 제거 (1. 2. 등)
                if line and not line.startswith("[") and not line.startswith("#"):
                    # "1. 제목" 형식에서 숫자 제거
                    import re
                    cleaned = re.sub(r'^\d+\.\s*', '', line)
                    if cleaned:
                        titles.append(cleaned)

            # 본문 섹션
            elif section == "body":
                if line:
                    body_lines.append(line)

        body = "\n".join(body_lines)

        return {
            "name": name,
            "category": category,
            "keywords": keywords,
            "titles": titles,
            "body": body
        }

    def interactive_add_template_from_link(self):
        """링크로 템플릿 생성 (GPT 창 이용)"""
        print("\n=== 링크/키워드로 템플릿 생성 ===")
        url_or_keyword = input("링크 또는 키워드 입력 (스킵하려면 엔터): ").strip()

        if url_or_keyword:
            category = input("카테고리 (선택, 엔터로 스킵): ").strip()
            self.create_template_from_link(url_or_keyword, category)

        print("\n" + "="*80)
        print("GPT에서 생성된 텍스트를 붙여넣으세요 (엔터 2번으로 종료):")
        print("="*80)

        # 여러 줄 입력 받기
        input_lines = []
        empty_count = 0
        while True:
            line = input()
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
                input_lines.append(line)
            else:
                empty_count = 0
                input_lines.append(line)

        full_text = "\n".join(input_lines)

        # 텍스트 파싱
        parsed = self.parse_gpt_output(full_text)

        if not parsed["name"]:
            print("❌ 템플릿 이름을 찾을 수 없습니다. 다시 시도해주세요.")
            return

        # 미리보기
        print("\n" + "="*80)
        print("📋 파싱된 템플릿 미리보기")
        print("="*80)
        print(f"이름: {parsed['name']}")
        print(f"카테고리: {parsed['category']}")
        print(f"키워드: {', '.join(parsed['keywords'])}")
        print(f"\n제목 ({len(parsed['titles'])}개):")
        for idx, title in enumerate(parsed['titles'], 1):
            print(f"  {idx}. {title}")
        print(f"\n본문 (길이: {len(parsed['body'])}자):")
        print(parsed['body'][:200] + "..." if len(parsed['body']) > 200 else parsed['body'])
        print("="*80)

        # 저장 확인
        save = input("\n이 템플릿을 저장하시겠습니까? (y/n): ").strip().lower()
        if save == 'y':
            self.add_template(
                parsed['name'],
                parsed['category'] or "기타",
                parsed['keywords'],
                parsed['titles'],
                parsed['body'],
                ["문의하기", "링크 확인"]
            )


def main():
    manager = DaangnAdTemplateManager()

    while True:
        print("\n" + "="*80)
        print("🥕 당근마켓 광고 템플릿 관리 시스템")
        print("="*80)
        print("1. 템플릿 목록 보기")
        print("2. 광고 생성 (템플릿 + 링크/키워드) + 복사")
        print("3. 새 템플릿 추가 (수동)")
        print("4. 새 템플릿 추가 (링크 → GPT 창 이용) 🤖")
        print("5. 템플릿 수정 ✏️")
        print("6. 템플릿 삭제")
        print("7. 템플릿 상세 보기")
        print("0. 종료")
        print("="*80)

        choice = input("\n선택: ").strip()

        if choice == "1":
            manager.list_templates()

        elif choice == "2":
            template_name = manager.select_template_by_number()
            if template_name:
                link = input("링크 URL (선택): ").strip()
                region = input("지역명 (선택): ").strip()
                ad_text = manager.generate_ad(template_name, link, region)

                if ad_text:
                    copy = input("\n📋 클립보드에 복사하시겠습니까? (y/n): ").strip().lower()
                    if copy == 'y':
                        try:
                            pyperclip.copy(ad_text)
                            print("✅ 클립보드에 복사되었습니다!")
                        except Exception as e:
                            print(f"❌ 복사 실패: {e}")

        elif choice == "3":
            manager.interactive_add_template()

        elif choice == "4":
            manager.interactive_add_template_from_link()

        elif choice == "5":
            template_name = manager.select_template_by_number()
            if template_name:
                manager.edit_template(template_name)

        elif choice == "6":
            template_name = manager.select_template_by_number()
            if template_name:
                confirm = input(f"정말 '{template_name}' 템플릿을 삭제하시겠습니까? (y/n): ").strip().lower()
                if confirm == 'y':
                    manager.delete_template(template_name)

        elif choice == "7":
            template_name = manager.select_template_by_number()
            if template_name:
                template = manager.get_template(template_name)
                if template:
                    print(f"\n=== {template_name} 상세 정보 ===")
                    print(json.dumps(template, ensure_ascii=False, indent=2))
                else:
                    print(f"❌ 템플릿 '{template_name}'을 찾을 수 없습니다.")

        elif choice == "0":
            print("\n👋 프로그램을 종료합니다.")
            break

        else:
            print("❌ 잘못된 선택입니다.")


if __name__ == "__main__":
    main()
