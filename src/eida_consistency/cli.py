import click
import logging
from eida_consistency.runner import run_consistency_check

@click.group()
def cli():
    pass

@cli.command()
@click.option('--node', required=True, help='EIDA node code (e.g., RESIF, NOA)')
@click.option('--epochs', default=10, show_default=True, help='Number of random epochs to test')
@click.option('--duration', default=600, show_default=True, help='Duration of each epoch in seconds')
@click.option('--seed', type=int, help='Seed for reproducible random selection')
@click.option('--delete-old', is_flag=True, help='Delete old reports, keep only the most recent N')
def consistency(node, epochs, duration, seed, delete_old):
    """Run availability + dataselect consistency check."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_consistency_check(
        node=node,
        epochs=epochs,
        duration=duration,
        seed=seed,
        delete_old=delete_old
    )

if __name__ == "__main__":
    cli()
