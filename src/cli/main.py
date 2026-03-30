import typer
from src.utils.helpers import logger

app = typer.Typer(help="PESync CLI - Gestión de backups de emulación", invoke_without_command=True)

@app.callback()
def main(ctx: typer.Context) -> None:
    """
    PESync: Sincronización inteligente de componentes de emulación.
    Si se ejecuta sin comandos, inicia la sincronización predeterminada.
    """
    if ctx.invoked_subcommand is None:
        sync()

@app.command()
def sync() -> None:
    """Ejecuta el flujo completo de sincronización y respaldo."""
    from src.core.backup_logic import main as core_sync
    core_sync()

@app.command()
def setup() -> None:
    """Lanza el asistente interactivo de configuración (Dropbox/Google Drive)."""
    from scripts.setup_storage import main as script_setup
    script_setup()

@app.command()
def test() -> None:
    """Realiza pruebas de salud y conectividad con los proveedores configurados."""
    from src.utils.health_checks import run_all_checks
    try:
        run_all_checks()
    except Exception as e:
        typer.secho(f"❌ Error en las pruebas: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def status() -> None:
    """Muestra el estado actual de los archivos en el almacenamiento remoto."""
    from src.providers.storage_providers import get_storage_provider
    from src.core.backup_logic import display_backup_summary
    
    provider = get_storage_provider()
    if not provider or not provider.connect():
        typer.secho("❌ No se pudo conectar al proveedor de almacenamiento.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    provider_name = provider.get_provider_name()
    logger.info(f"[{provider_name}] Obteniendo estado remoto...")
    backed_up = provider.list_files()
    display_backup_summary(backed_up)

if __name__ == "__main__":
    app()
