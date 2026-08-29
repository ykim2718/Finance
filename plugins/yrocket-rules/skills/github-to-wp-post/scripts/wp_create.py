#!/usr/bin/env python3
"""Create one WordPress post that points at a markdown file on GitHub.

The credentials are read from the environment:

    WP_URL, WP_USERNAME, WP_APP_PASSWORD

WP_APP_PASSWORD is a WordPress application password, not the login password.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 60
RETRIES = 4
TAG = 'github-hosted'


def _config() -> tuple:
    """Read the site URL and the credentials, failing loudly when one is absent."""
    missing = [k for k in ('WP_URL', 'WP_USERNAME', 'WP_APP_PASSWORD')
               if not os.environ.get(k)]
    if missing:
        sys.exit(
            'WordPress 자격증명이 설정되지 않았습니다. 프롬프트 창 위의 Trusted network '
            '표시를 눌러\n클라우드 환경 설정을 열고, 그 환경의 Environment variables 에 '
            '아래 세 개를 등록한 뒤\n새 session 에서 다시 요청해 주세요.\n\n'
            '  WP_URL           https://ykim.synology.me/wordpress\n'
            '  WP_USERNAME      로그인 계정\n'
            '  WP_APP_PASSWORD  xxxx xxxx xxxx xxxx xxxx xxxx\n\n'
            'application password 는 WP 관리자 → 사용자 → 프로필 → '
            '애플리케이션 비밀번호에서 발급합니다.\n'
            f"missing: {', '.join(missing)}")
    base = os.environ['WP_URL'].rstrip('/') + '/wp-json/wp/v2'
    token = base64.b64encode(
        f"{os.environ['WP_USERNAME']}:{os.environ['WP_APP_PASSWORD']}".encode()).decode()
    return base, token


def _decode(body: str = None):
    """Parse a response that a misbehaving plugin may have prefixed with noise."""
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start = min((i for i in (body.find('['), body.find('{')) if i > 0), default=-1)
        if start < 0:
            raise
        return json.loads(body[start:])


def call(path: str = None, params: dict = None, payload: dict = None) -> tuple:
    """Send one request and return the decoded body together with the headers.

    A read is retried through a transient proxy failure; a write is sent once.
    """
    base, token = _config()
    url = f"{base}/{path.lstrip('/')}"
    if params:
        url += '?' + urllib.parse.urlencode(params)
    data = json.dumps(payload).encode() if payload is not None else None
    attempts = 1 if data else RETRIES
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
        request.add_header('Authorization', f'Basic {token}')
        if data:
            request.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read().decode()
                if not body.strip():
                    raise ValueError('empty response body')
                return _decode(body), dict(response.headers)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors='replace')
            if error.code not in (429, 500, 502, 503, 504) or attempt == attempts:
                sys.exit(f"HTTP {error.code} on {path}: {detail[:500]}")
        except (urllib.error.URLError, ValueError, TimeoutError) as error:
            if attempt == attempts:
                sys.exit(f"{path} failed after {attempts} attempts: {error}")
        time.sleep(2 ** attempt)


def cmd_whoami(args) -> None:
    """Confirm the credentials before anything is written."""
    me, _ = call('users/me', {'context': 'edit'})
    caps = me.get('capabilities', {})
    print(json.dumps({
        'id': me['id'],
        'slug': me['slug'],
        'roles': me.get('roles'),
        'can_publish': bool(caps.get('publish_posts')),
    }, ensure_ascii=False, indent=2))
    if not caps.get('publish_posts'):
        sys.exit('이 계정은 publish_posts 권한이 없어 post 를 만들 수 없습니다.')


def parse_md_url(md_url: str = None) -> dict:
    """Split a GitHub blob URL into the values the shortcode and the raw fetch need."""
    parts = urllib.parse.urlparse(md_url).path.strip('/').split('/')
    if len(parts) < 5 or parts[2] not in ('blob', 'raw'):
        sys.exit(f"not a GitHub file URL: {md_url}")
    owner, repo, _, branch = parts[0], parts[1], parts[2], parts[3]
    file_path = '/'.join(parts[4:])
    return {'owner': owner, 'repo': repo, 'branch': branch, 'file_path': file_path,
            'raw_url': f'https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}'}


def cmd_parse(args) -> None:
    """Report the shortcode values taken from a markdown URL."""
    print(json.dumps(parse_md_url(args.md_url), indent=2))


def resolve_categories(names: str = None) -> dict:
    """Match requested category names against the registered ones.

    A name that matches nothing is dropped rather than created, so a typo adds
    no taxonomy to the site.
    """
    wanted = [n.strip() for n in (names or '').split(',') if n.strip()]
    if not wanted:
        return {'ids': [], 'matched': [], 'skipped': []}
    registered, page, terms = [], 1, None
    while True:
        terms, headers = call('categories', {'per_page': 100, 'page': page,
                                             '_fields': 'id,name,slug'})
        registered.extend(terms)
        if page >= int(headers.get('X-WP-TotalPages', 1)):
            break
        page += 1
    by_name = {t['name'].casefold(): t for t in registered}
    by_slug = {t['slug'].casefold(): t for t in registered}
    ids, matched, skipped = [], [], []
    for name in wanted:
        term = by_name.get(name.casefold()) or by_slug.get(name.casefold())
        if term:
            ids.append(term['id'])
            matched.append(term['name'])
        else:
            skipped.append(name)
    return {'ids': ids, 'matched': matched, 'skipped': skipped}


def resolve_author(value: str = None) -> int:
    """Turn a login, slug, display name, email or numeric id into a user id.

    Without this the post is authored by whoever the application password belongs
    to, which is a property of the credentials rather than a choice.
    """
    value = (value or '').strip()
    if value.isdigit():
        user, _ = call(f'users/{int(value)}', {'context': 'edit', '_fields': 'id'})
        return user['id']
    users, page, wanted = [], 1, value.casefold()
    while True:
        found, headers = call('users', {'per_page': 100, 'page': page, 'context': 'edit',
                                        '_fields': 'id,username,slug,name,email'})
        users.extend(found)
        if page >= int(headers.get('X-WP-TotalPages', 1)):
            break
        page += 1
    hits = [u for u in users
            if wanted in {(u.get(k) or '').casefold()
                          for k in ('username', 'slug', 'name', 'email')}]
    if not hits:
        sys.exit(f"author {value!r} 에 해당하는 사용자가 없습니다. "
                 f"login, slug, 이름, email 또는 id 로 지정하세요.")
    if len({u['id'] for u in hits}) > 1:
        sys.exit(f"author {value!r} 가 여러 사용자와 맞습니다: "
                 + json.dumps([{'id': u['id'], 'slug': u['slug']} for u in hits]))
    return hits[0]['id']


def resave_post(post_id: int = None) -> None:
    """Write the post's own content back to it, changing nothing.

    The site builds the featured image from the body image on a save after the
    first one, so a post is left without one until it is written a second time.
    """
    post, _ = call(f'posts/{post_id}', {'context': 'edit', '_fields': 'content'})
    call(f'posts/{post_id}', {'_fields': 'id'}, {'content': post['content']['raw']})


def cmd_resave(args) -> None:
    """Save a post again so the site fills in a missing featured image."""
    resave_post(args.post_id)
    post, _ = call(f'posts/{args.post_id}', {'_fields': 'id,featured_media,modified'})
    print(json.dumps(post, ensure_ascii=False, indent=2))


def align_featured_media(post_id: int = None, author_id: int = None,
                         tries: int = 4) -> dict:
    """Give the post's featured image the same author, once one exists.

    The site does not build it during the create call, so the first empty read is
    answered with one plain re-save rather than more waiting. Absence after that
    is not an error: the skill never uploads an image itself.
    """
    for attempt in range(tries):
        post, _ = call(f'posts/{post_id}', {'_fields': 'featured_media'})
        media_id = post.get('featured_media') or 0
        if media_id:
            media, _ = call(f'media/{media_id}', {'context': 'edit', '_fields': 'id,author,slug'})
            body = {}
            if media['author'] != author_id:
                body['author'] = author_id
            if media['slug'] != str(media_id):
                body['slug'] = str(media_id)
            if body:
                media, _ = call(f'media/{media_id}', {'_fields': 'id,author,slug'}, body)
            return {'id': media['id'], 'author': media['author'], 'slug': media['slug']}
        if attempt == 0:
            resave_post(post_id)
        elif attempt < tries - 1:
            time.sleep(1)
    return {}


def ensure_tag() -> int:
    """Return the id of the github-hosted tag, creating the term when absent."""
    found, _ = call('tags', {'slug': TAG, '_fields': 'id,slug'})
    if found:
        return found[0]['id']
    created, _ = call('tags', None, {'name': TAG, 'slug': TAG})
    return created['id']


def cmd_create(args) -> None:
    """Create the post from the pieces the skill has already prepared."""
    ref = parse_md_url(args.md_url)
    title = args.title
    excerpt = (sys.stdin.read() if args.excerpt_file == '-'
               else open(args.excerpt_file, encoding='utf-8').read()).strip()
    if not excerpt:
        sys.exit('excerpt is empty; write the summary before creating the post')

    duplicate, _ = call('posts', {'context': 'edit', 'status': 'any', 'per_page': 100,
                                  'search': ref['file_path'], '_fields': 'id,title,link'})
    if duplicate and not args.allow_duplicate:
        sys.exit('이 markdown 을 이미 쓰는 post 가 있습니다: '
                 + json.dumps([{'id': p['id'], 'link': p['link']} for p in duplicate],
                              ensure_ascii=False))

    content = (
        '<!-- wp:image {"width":"auto","height":"500px","sizeSlug":"large"} -->\n'
        '<figure class="wp-block-image size-large is-resized">'
        f'<img src="{args.image_url}" alt="" style="width:auto;height:500px"/></figure>\n'
        '<!-- /wp:image -->\n'
        '\n'
        '<!-- wp:shortcode -->\n'
        f"[github_file user='{ref['owner']}' repo='{ref['repo']}' file='{ref['file_path']}']\n"
        '<!-- /wp:shortcode -->')

    categories = resolve_categories(args.categories)
    author_id = resolve_author(args.author) if args.author else None
    payload = {'title': title, 'content': content, 'excerpt': excerpt,
               'status': args.status, 'tags': [ensure_tag()]}
    if categories['ids']:
        payload['categories'] = categories['ids']
    if author_id:
        payload['author'] = author_id

    post, _ = call('posts', {'context': 'edit'}, payload)
    result = {
        'id': post['id'],
        'status': post['status'],
        'link': post['link'],
        'title': post['title']['raw'],
        'author': post['author'],
        'excerpt_words': len(post['excerpt']['raw'].split()),
        'categories_applied': categories['matched'],
        'categories_skipped': categories['skipped'],
        'shortcode_file': ref['file_path'],
    }
    if author_id:
        result['featured_media'] = align_featured_media(post['id'], author_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    who = sub.add_parser('whoami', help='verify the credentials and the permission')
    who.set_defaults(func=cmd_whoami)

    parse = sub.add_parser('parse', help='split a GitHub markdown URL')
    parse.add_argument('md_url')
    parse.set_defaults(func=cmd_parse)

    create = sub.add_parser('create', help='create the post')
    create.add_argument('--md-url', required=True)
    create.add_argument('--image-url', required=True)
    create.add_argument('--title', required=True)
    create.add_argument('--excerpt-file', required=True,
                        help='file holding the excerpt, or - for stdin')
    create.add_argument('--categories', default='')
    create.add_argument('--author', default='',
                        help='post author as a login, slug, name, email or id; '
                             'defaults to the account the credentials belong to')
    create.add_argument('--status', default='draft', choices=('draft', 'publish'))
    create.add_argument('--allow-duplicate', action='store_true')
    create.set_defaults(func=cmd_create)

    resave = sub.add_parser('resave', help='save a post again to fill in a missing '
                                           'featured image; the content is unchanged')
    resave.add_argument('post_id', type=int)
    resave.set_defaults(func=cmd_resave)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
