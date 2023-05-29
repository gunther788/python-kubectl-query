from click.testing import CliRunner

from kubectl_query import main


def test_main():
    runner = CliRunner()
    result = runner.invoke(main, ['-vvv'])
    assert result.exit_code == 0
