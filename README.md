# 📚 AI 기반 논문 검색 및 연구동향 분석 시스템

## 실제 배포 URL 
http://calfadventure.com:8000/

## 🚀 프로젝트 소개

본 프로젝트는 **AI 기반 논문 검색 및 연구동향 분석 시스템**으로,
사용자가 원하는 논문을 빠르고 정확하게 탐색하고,
관련 연구 트렌드를 분석할 수 있도록 설계되었습니다.

기존 단순 키워드 검색의 한계를 개선하기 위해
**BERT 임베딩 + TF-IDF **을 결합하여
보다 정교한 검색 결과를 제공합니다.

---

## 🛠 기술 스택

| 구분       | 기술                          |
| -------- | --------------------------- |
| Backend  | Python, Django              |
| Frontend | HTML, CSS, JavaScript, Ajax |
| Database | MariaDB                     |
| AI       | BERT, TF-IDF                |
| Infra    | GitHub                      |

---

## 🎯 주요 기능

### 🔍 통합 검색 시스템

* 논문 / 저자 / 기관 / 국가 / 키워드 통합 검색
* 필터링 및 정렬 기능 제공
* Ajax 기반 비동기 처리

### 🤖 AI 기반 검색

* BERT 임베딩을 활용한 의미 기반 검색
* 키워드 일치가 아닌 문맥 기반 검색 지원

### 📊 연구 동향 분석

* TF-IDF + 인용수 기반 추천 키워드
* 워드클라우드를 통한 시각화 제공

### ⭐ 사용자 기능

* 논문 좋아요 기능
* 내 서재 저장 기능
* 로그인 기반 개인화 서비스

### ⚡ 사용자 경험 (UX)

* Ajax 기반 부분 렌더링
* 페이지 새로고침 없이 실시간 결과 반영

---

## 🏗 시스템 아키텍처

```
[ Client ]
   ↓ (Ajax 요청)
[ Django Server ]
   ├── 검색 로직 (TF-IDF, BERT)
   ├── 사용자 기능 처리
   ↓
[ MariaDB ]
   ↓
[ 결과 반환 (JSON / HTML Partial) ]
```

---

## 📂 프로젝트 구조

```
project/
│── search/
│   ├── views.py
│   ├── models.py
│   ├── templates/
│   │   ├── searchpage.html
│   │   ├── partials/
│── static/
│── db/
│── manage.py
```

---

## ⚙️ 실행 방법

### 1️⃣ 프로젝트 클론

```bash
git clone https://github.com/your-repo.git
cd your-repo
```

### 2️⃣ 가상환경 설정

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3️⃣ 패키지 설치

```bash
pip install -r requirements.txt
```

### 4️⃣ DB 설정 (MariaDB)

```sql
CREATE DATABASE paper_db;
```

`settings.py` 수정:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'paper_db',
        'USER': 'root',
        'PASSWORD': '비밀번호',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}
```

### 5️⃣ 서버 실행

```bash
python manage.py runserver
```

---

## 📸 실행 화면(메인 화면)

<img width="170" height="207" alt="image" src="https://github.com/user-attachments/assets/9fad1a68-95ae-4a54-a4d2-0a6e50930067" />

---

## 👨‍💻 담당 역할

* 전체 시스템 아키텍처 설계
* Django 기반 백엔드 로직 구현 및 데이터 처리
* MariaDB 데이터베이스 설계 및 관리
* 검색 결과 페이지 UI/UX 설계 및 구현
* Ajax 기반 비동기 통신을 활용한 동적 검색 기능 구현

---

## 📝 License

This project is for academic purposes.
