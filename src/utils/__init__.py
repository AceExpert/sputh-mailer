import string, random

def gen_token(length: int = 10):

    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length))