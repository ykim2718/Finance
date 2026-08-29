---
name: github-to-wp-post
description: GitHub 의 markdown file 을 가리키는 WordPress post 를 새로 만든다. 본문은 image block 과 [github_file] shortcode 두 개뿐이며, title 은 markdown 의 H1, excerpt 는 그 내용을 영어 50 단어로 요약한 것이고, tag 는 github-hosted 다. "md 를 wordpress post 로 등록해줘", "이 github 문서로 post 만들어줘", "github markdown 을 wordpress 에 올려줘" 같은 요청에 사용한다. 새 post 를 만드는 작업이며, 이미 있는 post 의 본문을 markdown 으로 옮기는 반대 방향은 wp-post-to-github 를 쓴다. "github to wp post 사용법 보여줘" 처럼 사용법을 물을 때도 이 skill 을 열어 section 2 를 보여준다.
---

# GitHub To WordPress Post
Rev. 9 | Created: 2026-08-21 | Updated: 2026-08-29 04:31 UTC

## 1. 작업대상

```text
- github markdown file url: <MD_URL>
- github image file url:    <IMAGE_URL>
- post category:            <CATEGORIES>
- post author:              <AUTHOR>
- post status:              <STATUS>
```

- `<IMAGE_URL>` 은 `https://github.com/<OWNER>/<REPO>/blob/main/<PATH>?raw=true` 형태로 쓴다.
  이 site 의 다른 post 가 모두 이 형태이다. `raw.githubusercontent.com` 주소도 그림은 똑같이
  보인다.
- `<CATEGORIES>` 는 comma separated string 이다. 예: `Data Science, EDA`
- `<AUTHOR>` 는 login, slug, 이름, email 또는 id 다. 주지 않으면 application password 의 주인이
  저자가 된다.
- `<STATUS>` 는 `draft` 또는 `publish` 다. 주지 않으면 `draft` 로 만들고 확인을 받는다.

## 2. Usage

사용자가 사용법을 물으면 인증 값을 두는 자리를 먼저 알려주고, 이어서 아래 prompt block 을 그대로
보여준다. `<...>` 자리만 채워 쓰라고 안내한다.

인증 값은 shell 에서 `export` 하지 않는다. session 이 끝나면 사라져 매번 다시 넣어야 하고, 명령
기록에 application password 가 그대로 남는다. 프롬프트 창 위의 **Trusted network** 표시를 눌러
클라우드 환경 설정을 열고, 그 환경의 **Environment variables** 에 아래 세 개를 등록한다. 한 번
등록하면 이후 새로 여는 session 에 자동으로 실린다.

| Variable | Value |
|----------|-------|
| `WP_URL` | `https://ykim.synology.me/wordpress` |
| `WP_USERNAME` | `<WP_USERNAME>` |
| `WP_APP_PASSWORD` | `xxxx xxxx xxxx xxxx xxxx xxxx` |

`WP_USERNAME` 은 application password 를 발급할 때 붙인 이름이 아니라 로그인 계정이다. 3 을 본다.
값을 고치면 이미 열려 있는 session 에는 반영되지 않으므로 새 session 을 연다.

```text
# Prompt Command
GitHub markdown을 WordPress post로 등록해줘
- github markdown file url: <MD_URL>
- github image file url: <IMAGE_URL>
- post category: <CATEGORIES>
- post author: <AUTHOR>
- post status: <STATUS>
```

함께 알려줄 것.

- `<IMAGE_URL>` 은 `https://github.com/<OWNER>/<REPO>/blob/main/<PATH>?raw=true` 형태로 준다.
  이 site 의 다른 post 가 모두 이 형태이다. 어느 형태든 본문의 그림은 똑같이 보인다.
- `<CATEGORIES>` 는 comma separated string 이다. 예: `Data Science, EDA`. 등록되지 않은 이름은
  생략되며 새 category 를 만들지 않는다.
- `<AUTHOR>` 는 login, slug, 이름, email 또는 id 로 준다. 주지 않으면 application password 의
  주인이 저자가 되므로, 글을 올리는 계정과 저자가 다르면 반드시 준다. 4.5 를 본다.
- `<STATUS>` 를 주지 않으면 `draft` 로 만들고 확인을 받는다.
- title 은 markdown 의 H1, excerpt 는 그 내용을 영어 50 단어로 요약한 것, tag 는
  `github-hosted` 로 자동 결정된다.
- 같은 markdown 을 이미 쓰는 post 가 있으면 만들지 않고 멈춘다.
- 반대 방향, 곧 이미 있는 post 의 본문을 markdown 으로 옮기는 작업은 `wp-post-to-github` 다.

## 3. WordPress User

인증은 환경변수로 읽는다. 등록하는 자리는 2 를 본다.

| Variable | Example | Note |
|----------|---------|------|
| `WP_URL` | `https://ykim.synology.me/wordpress` | WordPress 설치의 주소. |
| `WP_USERNAME` | `<WP_USERNAME>` | 로그인 계정이다. `invalid_username` 이 돌아오면 email 로 다시 시도한다. |
| `WP_APP_PASSWORD` | `xxxx xxxx xxxx xxxx xxxx xxxx` | application password 이며 로그인 비밀번호가 아니다. |

값을 대화에 다시 적지 않는다.

**세 변수 중 하나라도 비어 있으면 아무 작업도 하지 않고 아래를 그대로 보이고 멈춘다.**
값을 짐작하거나 다른 계정으로 대신하지 않는다.

```text
WordPress 자격증명이 설정되지 않았습니다. 프롬프트 창 위의 Trusted network 표시를 눌러
클라우드 환경 설정을 열고, 그 환경의 Environment variables 에 아래 세 개를 등록한 뒤
새 session 에서 다시 요청해 주세요.

  WP_URL           https://ykim.synology.me/wordpress
  WP_USERNAME      로그인 계정
  WP_APP_PASSWORD  xxxx xxxx xxxx xxxx xxxx xxxx

application password 는 WP 관리자 → 사용자 → 프로필 → 애플리케이션 비밀번호에서 발급합니다.
```

script 는 절대 경로로 부른다. skill 이 plugin 으로 로드되면 작업 directory 가 skill folder 가
아니다. 아래를 한 번 정해 두고 이후 `$WPGP` 로 쓴다.

```bash
WPGP="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github-to-wp-post/scripts"
test -f "$WPGP/wp_create.py" || WPGP=".claude/skills/github-to-wp-post/scripts"
```

설정되어 있으면 작업 전에 한 번 확인한다. 여기서 실패하면 뒤 step 을 진행하지 않는다.

```bash
python3 "$WPGP"/wp_create.py whoami
```

- `401 invalid_username` → `WP_USERNAME` 이 로그인 계정이 아니다. 발급할 때 붙인 **이름**을 넣은
  경우가 많다. email 을 시도하고, 그래도 실패하면 사용자에게 알린다.
- `401 incorrect_password` → application password 가 틀렸거나 폐기되었다.
- 응답의 `capabilities` 에 `publish_posts` 가 없으면 post 를 만들 수 없다. 어떤 권한이
  모자란지 알리고 멈춘다.

## 4. 작업 순서

각 step 을 마칠 때마다 진행 상태와 만들어진 값(post id, permalink) 을 화면에 보인다.

### 4.1 Step 1 — 입력 확인

1. `<MD_URL>` 의 raw 를 받아 읽는다. `blob` 을 `raw` 로 바꾸거나 `?raw=true` 를 붙인다.
   받지 못하면 멈추고 알린다. 없는 문서로 post 를 만들지 않는다.
2. `<IMAGE_URL>` 이 200 과 `image/*` 를 돌려주는지 확인한다. 형태가
   `https://github.com/<OWNER>/<REPO>/blob/main/<PATH>?raw=true` 가 아니면 그 형태로 바꾸어
   쓰고 사용자에게 알린다.
3. `<MD_URL>` 에서 shortcode 에 넣을 값을 뽑는다.

   ```bash
   python3 "$WPGP"/wp_create.py parse '<MD_URL>'
   ```

   `https://github.com/ykim2718/AIML/blob/main/EDA/Noise/noise-color-taxonomy.md` 이면
   `repo` 는 `AIML`, `file_path` 는 `EDA/Noise/noise-color-taxonomy.md`, `raw_url` 은
   그 문서를 내려받을 주소다.

### 4.2 Step 2 — Title 과 Category

1. post title 은 markdown 의 H1 을 그대로 쓴다. `Rev.` 표시 줄은 제외한다.
2. category 대조는 Step 5 의 `--categories` 가 맡는다. 등록된 이름과 대조해 대소문자만 다른
   것은 같은 것으로 보고, **맞지 않는 이름은 생략한다. 새 category 를 만들지 않는다.**
   결과의 `categories_applied` 와 `categories_skipped` 를 사용자에게 보고한다.

### 4.3 Step 3 — Excerpt

`<MD_URL>` 의 내용을 읽고 **영어 50 단어 수준**으로 요약해 excerpt 로 등록한다.

- 문서의 결론을 한두 문장으로 적는다. 제목을 되풀이하지 않는다.
- markup 없는 평문으로 쓴다.

### 4.4 Step 4 — Post 본문

본문은 정확히 아래 두 block 이며, image block 이 먼저이고 shortcode block 이 그 아래다.

```html
<!-- wp:image {"width":"auto","height":"500px","sizeSlug":"large"} -->
<figure class="wp-block-image size-large is-resized"><img src="<IMAGE_URL>" alt="" style="width:auto;height:500px"/></figure>
<!-- /wp:image -->

<!-- wp:shortcode -->
[github_file user='ykim2718' repo='<REPO>' file='<FILE_PATH>']
<!-- /wp:shortcode -->
```

- image 는 media library 에 올리지 않는다. `<IMAGE_URL>` 을 그대로 media URL 로 쓴다.
- height 는 500px 로 고정하고 width 는 `auto` 로 둔다.

### 4.5 Step 5 — 등록

한 번의 요청으로 만든다. title, content, excerpt, categories, tags, status, author 가 함께 간다.

```bash
python3 "$WPGP"/wp_create.py create \
    --md-url '<MD_URL>' \
    --image-url '<IMAGE_URL>' \
    --title '<TITLE>' \
    --excerpt-file "$SCRATCH/excerpt.txt" \
    --categories '<CATEGORIES>' \
    --author '<AUTHOR>' \
    --status '<STATUS>'
```

- `--author` 는 login, slug, 이름, email 또는 id 로 받는다. **주지 않으면 application password
  의 주인이 저자가 된다.** 저자는 자격증명의 성질이지 선택이 아니므로, 글을 올리는 계정과 저자가
  다르면 반드시 준다. 맞는 사용자가 없거나 여럿이면 만들지 않고 멈춘다.
- `--author` 를 준 경우, featured image 까지 script 가 맡는다. 사이트는 그것을 첫 저장이 아니라
  그 다음 저장에서 만들므로, script 가 비어 있는 것을 보면 본문을 그대로 한 번 더 저장한 뒤
  생긴 image 의 author 와 slug 를 맞춘다. 그래도 생기지 않는 것은 오류가 아니다. 이 skill 은
  image 를 media library 에 올리지 않는다.
- 본문 두 block 은 script 가 위 형식 그대로 만든다. 직접 조립하지 않는다.
- tag 는 `github-hosted` 하나가 붙는다. term 이 없으면 만들어 붙인다.
  (WordPress tag 이름에 `#` 은 쓰지 않는다.)
- 같은 `<FILE_PATH>` 를 쓰는 post 가 이미 있으면 만들지 않고 멈춘다. 그 post 를 사용자에게
  알린다. 그래도 새로 만들어야 한다면 `--allow-duplicate` 를 준다.

## 5. Verification

1. 만들어진 permalink 를 로그인 없이 받는다.
   - `[github_file` 문자열이 **보이지 않아야** 한다. 보이면 shortcode 가 실행되지 않은 것이다.
   - markdown 의 heading 이 보여야 한다.
   - `height:500px` 가 있어야 한다.
2. `featured_media` 가 0 이 아닌지 본다. 이 site 의 다른 post 는 모두 featured image 를 가지고
   있고, 없으면 목록 page, archive, 공유 카드의 thumbnail 이 빈다.

   **0 이면 본문을 그대로 한 번 더 저장한다.** 이 site 는 featured image 를 처음 만들 때가 아니라
   그 다음 저장에서 만든다. 내용을 바꿀 필요가 없으므로 읽은 `content` 를 그대로 돌려보낸다.
   image 의 URL 형태와는 무관하다.

   ```bash
   python3 "$WPGP"/wp_create.py resave <ID>
   ```

   그래도 0 이면 사용자에게 알린다. 이 skill 은 image 를 media library 에 올리지 않는다.
3. post id, permalink, 적용된 category, author, featured image, excerpt 단어 수를 보고한다.

## 6. Scope Rules

- 한 번에 markdown 하나만 다룬다.
- 기존 post 를 고치지 않는다. 이 지시서는 **새 post 를 만드는 작업**이다.
- markdown 본문을 post 본문으로 옮겨 붙이지 않는다. 본문은 위의 두 block 뿐이다.
- category 를 새로 만들지 않는다.

## 7. Maintenance

- H1 바로 아래의 `Rev. <N> | Created: <YYYY-MM-DD> | Updated: <YYYY-MM-DD HH:MM> <TIMEZONE>`
  표시를 **수정할 때마다 갱신한다.** `N` 은 1 씩 올리고 `Updated` 는 지금 시각으로 바꾼다.
  `Created` 는 바꾸지 않는다. timezone 은 `date +%Z` 로 읽는다.
- skill 로 등록해 쓰는 경우, 고친 뒤에는 marketplace plugin 사본에도 복사하고 두 곳 모두
  push 한다. 한쪽만 고치면 세션이 어디서 시작했는지에 따라 다른 것이 로드된다.
