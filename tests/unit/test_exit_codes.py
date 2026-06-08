from zotero_cli.utils import exit_codes


def test_success_is_zero() -> None:
    assert exit_codes.EXIT_SUCCESS == 0


def test_user_error_is_one() -> None:
    assert exit_codes.EXIT_USER_ERROR == 1


def test_network_error_is_two() -> None:
    assert exit_codes.EXIT_NETWORK_ERROR == 2


def test_auth_error_is_three() -> None:
    assert exit_codes.EXIT_AUTH_ERROR == 3


def test_local_error_is_four() -> None:
    assert exit_codes.EXIT_LOCAL_ERROR == 4


def test_usage_error_is_64() -> None:
    assert exit_codes.EXIT_USAGE_ERROR == 64


def test_interrupted_is_130() -> None:
    assert exit_codes.EXIT_INTERRUPTED == 130
