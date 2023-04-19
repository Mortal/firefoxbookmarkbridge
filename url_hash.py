# https://gist.github.com/boppreh/a9737acb2abf015e6e828277b40efe71
golden_ratio = 0x9E3779B9
max_int = 2**32 - 1

def rotate_left_5(value):
    return ((value << 5) | (value >> 27)) & max_int

def add_to_hash(hash_value, value):
    return (golden_ratio * (rotate_left_5(hash_value) ^ value))  & max_int

def hash_simple(url):
    hash_value = 0
    for char in url.encode('utf-8'):
        hash_value = add_to_hash(hash_value, char)
    return hash_value

def url_hash(url):
    prefix, _ = url.split(':', 1)
    return ((hash_simple(prefix) & 0x0000FFFF) << 32) + hash_simple(url)

if __name__ == '__main__':
    assert url_hash("http://example.org/") == 125508604170377
    assert url_hash("https://example.org/") == 47358175329495
    assert url_hash("https://www.reddit.com/") == 47359719085711
    assert url_hash("https://old.reddit.com/") == 47358033120677
    assert url_hash("https://en.wikipedia.org/wiki/Libert%C3%A9") == 47359238090423
