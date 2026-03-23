# 🚀 Guía de Uso: PESync CLI

Ahora PESync cuenta con una interfaz unificada. Puedes usarla directamente desde la terminal o mediante los accesos directos `.bat` que he creado para ti.

## 🖱️ Accesos Directos (Windows)

He creado 4 archivos `.bat` en la raíz del proyecto para que no tengas que escribir comandos:

| Archivo | Función | Cuándo usarlo |
| :--- | :--- | :--- |
| `iniciar_pesync.bat` | **Sincronización Total** | El uso diario para respaldar todo. |
| `pesync_setup.bat` | **Configuración** | Para cambiar de Dropbox a Google Drive o renovar tokens. |
| `pesync_test.bat` | **Prueba de Salud** | Si algo falla, úsalo para ver si el problema es de red o credenciales. |
| `pesync_status.bat` | **Resumen Remoto** | Para ver qué versiones tienes guardadas en la nube rápidamente. |

---

## 💻 Uso desde la Terminal

Si prefieres la terminal, ahora tienes comandos claros. Asegúrate de estar en la carpeta del proyecto:

### 1. Sincronización (Predeterminado)

```bash
python main.py
# o también:
python main.py sync
```

### 2. Ver estado de la nube

```bash
python main.py status
```

### 3. Asistente de configuración

```bash
python main.py setup
```

### 4. Diagnóstico de conexión

```bash
python main.py test
```

### 5. Ayuda detallada

```bash
python main.py --help
```

---

## ⚙️ ¿Por qué este cambio?
Esta nueva estructura permite que el bot de **GitHub Actions** siga funcionando sin cambios, mientras que a ti te da herramientas de diagnóstico mucho más rápidas y precisas. ¡Disfruta de tu nuevo "tablero de control"!
