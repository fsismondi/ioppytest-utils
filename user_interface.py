import click
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.contrib.completers import WordCompleter

SQLCompleter = WordCompleter(['select', 'from', 'insert', 'update', 'delete', 'drop'],
                             ignore_case=True)


if __name__ == '__main__':
    cli = click.Group(
        short_help='hola'
    )

    session_url = click.Option(
        param_decls=["--url"],
        default="amqp://guest:guest@localhost/",
        required=True,
        help="AMQP url provided by F-Interop")

    connect_command = click.Command(
        "connect",
        callback=print,
        params=[
            session_url,
        ],
        short_help="Connect with authentication AMQP_URL, and some other basic agent configurations."
    )

    cli.add_command(connect_command)


    while 1:
        user_input = prompt('SQL>',
                            history=FileHistory('history.txt'),
                            auto_suggest=AutoSuggestFromHistory(),
                            completer=SQLCompleter,
                            )
        print('# entered: ' + user_input)
        #click.echo_via_pager(user_input)

        try:
            cli()
        except Exception as e:
            print(e)