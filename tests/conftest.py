"""Platform capabilities shared by the regression suites."""
import pytest


@pytest.fixture
def make_symlink():
    def create(link, target, *, target_is_directory=False):
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 1314:
                pytest.skip('Windows account lacks permission to create symbolic links')
            raise
        return link
    return create
