#!/usr/bin/env python3
"""Minimal WordPress REST client for the wp-post-to-github skill.

Credentials come from the environment so that an application password is never
written into a command line, a file, or the conversation:

    WP_URL, WP_USERNAME, WP_APP_PASSWORD
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


def _config() -> tuple:
    """Read the site URL and the credentials, failing loudly when one is absent.

    The account is WP_USERNAME. The earlier name WP_USER is not read: accepting
    both leaves a stale value working silently after the rename.
    """
    missing = [k for k in ('WP_URL', 'WP_USERNAME', 'WP_APP_PASSWORD')
               if not os.environ.get(k)]
    if missing:
        hint = ('\n(WP_USER is set but no longer read; register WP_USERNAME in the '
                'cloud environment instead.)'
                if 'WP_USERNAME' in missing and os.environ.get('WP_USER') else '')
        sys.exit(f"missing environment variable(s): {', '.join(missing)}{hint}")
    user = os.environ['WP_USERNAME']
    base = os.environ['WP_URL'].rstrip('/') + '/wp-json/wp/v2'
    token = base64.b64encode(
        f"{user}:{os.environ['WP_APP_PASSWORD']}".encode()).decode()
    return base, token


def _decode(body: str = None):
    """Parse a REST response that a misbehaving plugin may have prefixed with noise.

    A plugin emitting a PHP warning writes it ahead of the JSON, so the payload
    no longer starts at byte 0. The warnings are printed before the body is
    flushed, so skipping to the first bracket recovers the response.
    """
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start = min((i for i in (body.find('['), body.find('{')) if i > 0), default=-1)
        if start < 0:
            raise
        return json.loads(body[start:])


def call(path: str = None, params: dict = None, payload: dict = None) -> tuple:
    """Send one request and return the decoded body together with the response headers.

    A proxy in front of the site occasionally answers a large listing with an
    empty body or a 502, so a transient failure is retried rather than raised.
    A read is safe to repeat; a write is sent once.
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


def resolve(reference: str = None) -> int:
    """Turn a post id, a slug, or a permalink into a post id."""
    reference = reference.strip().rstrip('/')
    if reference.isdigit():
        return int(reference)
    slug = reference.split('/')[-1]
    posts, _ = call('posts', {'slug': slug, 'context': 'edit', 'status': 'any'})
    if posts:
        return posts[0]['id']
    tail = slug.rsplit('-', 1)[-1]          # permalinks often end in the post id
    if tail.isdigit():
        return int(tail)
    sys.exit(f"could not resolve a post from {reference!r}")


def cmd_get(args) -> None:
    post, _ = call(f'posts/{resolve(args.post)}', {'context': 'edit'})
    if args.raw:
        sys.stdout.write(post['content']['raw'])
        return
    print(json.dumps({
        'id': post['id'],
        'slug': post['slug'],
        'status': post['status'],
        'title': post['title']['raw'],
        'date': post['date'],
        'modified': post['modified'],
        'link': post['link'],
        'content_length': len(post['content']['raw']),
    }, ensure_ascii=False, indent=2))


def cmd_revisions(args) -> None:
    """Report the values the document header is built from.

    The Rev number is one less than the X-WP-Total of the revisions listing,
    because the first stored revision is Rev. 0. Run before the body is
    replaced, take x_wp_total instead: the replacement adds the revision that
    the subtraction would otherwise remove. The Created date is the date the
    post was published rather than the date it was converted.
    """
    post_id = resolve(args.post)
    _, headers = call(f'posts/{post_id}/revisions', {'context': 'edit', 'per_page': 1})
    total = int(headers.get('X-WP-Total', 0))
    post, _ = call(f'posts/{post_id}', {'context': 'edit', '_fields': 'date'})
    print(json.dumps({
        'x_wp_total': total,
        'rev_number': max(total - 1, 0),     # the first stored revision is Rev. 0
        'created': post['date'][:10],
    }, indent=2))


def cmd_search(args) -> None:
    for post_type in args.types.split(','):
        params = {'search': args.query, 'context': 'edit', 'per_page': 100,
                  '_fields': 'id,status,title,link'}
        # The media endpoint rejects status=any; an attachment carries its own enum.
        if post_type != 'media':
            params['status'] = 'any'
        found, _ = call(post_type, params)
        for post in found:
            print(f"{post_type}\t{post['id']}\t{post['status']}\t{post['title']['raw']}")


def ensure_tag(slug: str = None) -> int:
    """Return the id of the tag with this slug, creating the term if it is absent."""
    found, _ = call('tags', {'slug': slug, 'context': 'edit'})
    if found:
        return found[0]['id']
    created, _ = call('tags', None, {'name': slug, 'slug': slug})
    return created['id']


def cmd_converted(args) -> None:
    """List the posts already converted, found by their tag or by the shortcode."""
    rows = []
    found, _ = call('tags', {'slug': args.tag, 'context': 'edit'})
    if found:
        page = 1
        while True:
            items, headers = call('posts', {'tags': found[0]['id'], 'context': 'edit',
                                            'status': 'any', 'per_page': 100, 'page': page,
                                            '_fields': 'id,title,link'})
            rows += [(p['id'], p['title']['raw'], p['link']) for p in items]
            if not items or page >= int(headers.get('X-WP-TotalPages', 1)):
                break
            page += 1
    if not rows:
        items, _ = call('posts', {'search': 'github_file', 'context': 'edit',
                                  'status': 'any', 'per_page': 100,
                                  '_fields': 'id,title,link'})
        rows = [(p['id'], p['title']['raw'], p['link']) for p in items]
    for row in rows:
        print('\t'.join(str(field) for field in row))
    print(f'-- {len(rows)} post(s)', file=sys.stderr)


def cmd_update(args) -> None:
    """Replace the body of one post, leaving every other field untouched.

    With --add-tag the tag rides along in the same request, so the conversion
    stays one revision rather than two.
    """
    post_id = resolve(args.post)
    content = (sys.stdin.read() if args.content_file == '-'
               else open(args.content_file, encoding='utf-8').read())
    payload = {'content': content}
    if args.excerpt_file:
        payload['excerpt'] = (sys.stdin.read() if args.excerpt_file == '-'
                              else open(args.excerpt_file, encoding='utf-8').read()).strip()
    if args.add_tag:
        current, _ = call(f'posts/{post_id}', {'context': 'edit', '_fields': 'tags'})
        tag_id = ensure_tag(args.add_tag)
        payload['tags'] = sorted(set(current.get('tags', []) + [tag_id]))
    post, _ = call(f'posts/{post_id}', {'context': 'edit'}, payload)
    print(json.dumps({
        'id': post['id'],
        'status': post['status'],
        'modified': post['modified'],
        'tags': post.get('tags'),
        'excerpt': post['excerpt']['raw'],
        'content': post['content']['raw'],
    }, ensure_ascii=False, indent=2))


def cmd_excerpt(args) -> None:
    """Read or set the excerpt of one post, leaving the body alone.

    A post whose excerpt field is empty falls back to an excerpt generated from
    the body. Once the body is a header image and a shortcode there is nothing
    to generate from, so the field has to hold real text.
    """
    post_id = resolve(args.post)
    if args.excerpt_file is None:
        post, _ = call(f'posts/{post_id}', {'context': 'edit', '_fields': 'excerpt'})
        text = post['excerpt']['raw']
        print(json.dumps({'id': post_id, 'excerpt': text,
                          'words': len(text.split()), 'empty': not text.strip()},
                         ensure_ascii=False, indent=2))
        return
    text = (sys.stdin.read() if args.excerpt_file == '-'
            else open(args.excerpt_file, encoding='utf-8').read()).strip()
    post, _ = call(f'posts/{post_id}', {'context': 'edit'}, {'excerpt': text})
    print(json.dumps({'id': post['id'], 'excerpt': post['excerpt']['raw'],
                      'words': len(post['excerpt']['raw'].split())},
                     ensure_ascii=False, indent=2))


def cmd_tag(args) -> None:
    """Attach a tag to one post without touching its body.

    A taxonomy change is not a post field, so this does not add a revision and
    the Rev number in the markdown stays correct. Use it to mark posts that
    were converted before the tag existed.
    """
    post_id = resolve(args.post)
    current, _ = call(f'posts/{post_id}', {'context': 'edit', '_fields': 'tags'})
    tag_id = ensure_tag(args.add_tag)
    if tag_id in current.get('tags', []):
        print(json.dumps({'id': post_id, 'tags': current['tags'], 'changed': False}))
        return
    post, _ = call(f'posts/{post_id}', {'context': 'edit'},
                   {'tags': sorted(set(current.get('tags', []) + [tag_id]))})
    print(json.dumps({'id': post['id'], 'tags': post['tags'], 'changed': True}))


def cmd_orphan_check(args) -> None:
    """Report every use of one attachment, so that a deletion is never a guess.

    The image is deleted while the post being converted still shows it, so that
    post's own body reference is expected and is excluded with --exclude-post.
    A reference from any other post, and any featured image assignment, still
    blocks: deleting a featured image drops the thumbnail from archive listings
    and from share cards.
    """
    media, _ = call(f'media/{args.attachment}', {'context': 'edit'})
    source = media['source_url']
    stem = source.rsplit('/', 1)[-1].rsplit('.', 1)[0]

    body_hits, featured_hits = [], []
    for post_type in args.types.split(','):
        page = 1
        while True:
            items, headers = call(post_type, {
                'context': 'edit', 'status': 'any', 'per_page': 100, 'page': page,
                '_fields': 'id,title,featured_media,content'})
            if not items:
                break
            for item in items:
                label = (post_type, item['id'], item['title']['raw'])
                if item.get('featured_media') == media['id']:
                    featured_hits.append(label)
                if item['id'] == args.exclude_post:
                    continue
                body = (item.get('content') or {}).get('raw', '')
                if stem in body or source in body:
                    body_hits.append(label)
            if page >= int(headers.get('X-WP-TotalPages', 1)):
                break
            page += 1

    print(json.dumps({
        'attachment': media['id'],
        'source_url': source,
        'excluded_post': args.exclude_post,
        'body_references': [list(h) for h in body_hits],
        'featured_image_of': [list(h) for h in featured_hits],
        'safe_to_delete': not body_hits and not featured_hits,
        'reason': ('featured image in use' if featured_hits
                   else 'referenced by another post' if body_hits
                   else 'no remaining use'),
    }, ensure_ascii=False, indent=2))


def cmd_delete_media(args) -> None:
    """Delete one attachment permanently. Run orphan-check first."""
    if not args.confirm:
        sys.exit('refusing to delete without --confirm')
    base, token = _config()
    url = f"{base}/media/{args.attachment}?force=true"
    request = urllib.request.Request(url, method='DELETE')
    request.add_header('Authorization', f'Basic {token}')
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            result = _decode(response.read().decode())
    except urllib.error.HTTPError as error:
        sys.exit(f"HTTP {error.code}: {error.read().decode(errors='replace')[:500]}")
    print(json.dumps({'deleted': result.get('deleted'),
                      'id': result.get('previous', {}).get('id')}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)

    get = sub.add_parser('get', help='print post metadata, or the raw body with --raw')
    get.add_argument('post')
    get.add_argument('--raw', action='store_true')
    get.set_defaults(func=cmd_get)

    revisions = sub.add_parser('revisions', help='print the revision count and Rev number')
    revisions.add_argument('post')
    revisions.set_defaults(func=cmd_revisions)

    search = sub.add_parser('search', help='find content carrying a string')
    search.add_argument('query')
    search.add_argument('--types', default='posts,pages,blocks')
    search.set_defaults(func=cmd_search)

    update = sub.add_parser('update', help='replace the body of one post')
    update.add_argument('post')
    update.add_argument('--content-file', required=True, help="file holding the new body, or -")
    update.add_argument('--excerpt-file', default=None,
                        help='file holding the excerpt to set, or - for stdin')
    update.add_argument('--add-tag', default=None,
                        help='tag slug to attach in the same request, e.g. github-hosted')
    update.set_defaults(func=cmd_update)

    excerpt = sub.add_parser('excerpt', help='read or set the excerpt of a post')
    excerpt.add_argument('post')
    excerpt.add_argument('--excerpt-file', default=None,
                         help='file holding the new excerpt, or - for stdin; omit to read')
    excerpt.set_defaults(func=cmd_excerpt)

    tag = sub.add_parser('tag', help='attach a tag to a post without touching the body')
    tag.add_argument('post')
    tag.add_argument('--add-tag', default='github-hosted')
    tag.set_defaults(func=cmd_tag)

    converted = sub.add_parser('converted', help='list posts already converted')
    converted.add_argument('--tag', default='github-hosted')
    converted.set_defaults(func=cmd_converted)

    orphan = sub.add_parser('orphan-check',
                            help='report body and featured-image uses of an attachment')
    orphan.add_argument('attachment', type=int)
    orphan.add_argument('--types', default='posts,pages')
    orphan.add_argument('--exclude-post', type=int, default=None,
                        help='id of the post being converted, whose body reference is expected')
    orphan.set_defaults(func=cmd_orphan_check)

    delete = sub.add_parser('delete-media', help='permanently delete an attachment')
    delete.add_argument('attachment', type=int)
    delete.add_argument('--confirm', action='store_true')
    delete.set_defaults(func=cmd_delete_media)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
