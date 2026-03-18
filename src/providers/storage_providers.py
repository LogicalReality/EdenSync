# pyre-ignore-all-errors[21]
"""
Módulo de proveedores de almacenamiento para PESync.
Proporciona una abstracción para soportar múltiples servicios de nube (Dropbox, Google Drive, etc.)
"""
from __future__ import annotations
import os
from abc import ABC, abstractmethod
from typing import Any, Set
import dropbox  # type: ignore
from dropbox.exceptions import ApiError  # type: ignore
from dropbox.files import WriteMode, UploadSessionCursor, CommitInfo  # type: ignore
import requests # type: ignore
import subprocess
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from src.utils.helpers import logger  # pyre-ignore[21]

# Tamaño de chunk (fijado a 32MB para alto rendimiento en conexiones modernas)
CHUNK_SIZE = 32 * 1024 * 1024

# ==========================================
# INTERFAZ ABSTRACTA DE PROVEEDOR
# ==========================================
class StorageProvider(ABC):
    """Clase abstracta que define la interfaz para proveedores de almacenamiento."""
    
    @abstractmethod
    def connect(self) -> bool:
        """Conecta al servicio de almacenamiento. Retorna True si la conexión fue exitosa."""
        return False
    
    @abstractmethod
    def list_files(self) -> set[str]:
        """Lista todos los archivos en el almacenamiento remoto."""
        return set()
    
    @abstractmethod
    def upload_file(self, local_path: str, remote_name: str) -> bool:
        """Sube un archivo al almacenamiento remoto."""
        return False

    @abstractmethod
    def upload_files(self, file_paths: list[str]) -> bool:
        """Sube una lista de archivos en paralelo."""
        return False
    
    @abstractmethod
    def delete_file(self, file_name: str) -> bool:
        """Elimina un archivo del almacenamiento remoto."""
        return False
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Retorna el nombre del proveedor."""
        return ""


# ==========================================
# PROVEEDOR DE DROPBOX
# ==========================================
class DropboxProvider(StorageProvider):
    """Implementación de StorageProvider para Dropbox."""
    
    def __init__(self):
        self.dbx: dropbox.Dropbox | None = None
    
    def connect(self) -> bool:
        """Inicializa el cliente de Dropbox."""
        try:
            app_key = os.environ["DROPBOX_APP_KEY"]
            app_secret = os.environ["DROPBOX_APP_SECRET"]
            refresh_token = os.environ["DROPBOX_REFRESH_TOKEN"]
        except KeyError as e:
            logger.error(f"Error: La variable de entorno {e} no está configurada.")
            return False
        
        try:
            self.dbx = dropbox.Dropbox(
                app_key=app_key,
                app_secret=app_secret,
                oauth2_refresh_token=refresh_token
            )
            logger.info("[DROPBOX] Cliente inicializado correctamente.")
            return True
        except Exception:
            logger.exception("Error al inicializar el cliente de Dropbox:")
            return False
    
    def list_files(self) -> set[str]:
        """Lista archivos en Dropbox."""
        if not self.dbx:
            logger.error("Cliente de Dropbox no inicializado.")
            return set()
        
        try:
            result = self.dbx.files_list_folder("")
            files: set[str] = {entry.name for entry in result.entries}
            while result.has_more:
                result = self.dbx.files_list_folder_continue(result.cursor)
                files.update(entry.name for entry in result.entries)
            return files
        except Exception:
            logger.exception("Error al listar archivos en Dropbox:")
            return set()
    
    def upload_file(self, local_path: str, remote_name: str) -> bool:
        """Sube un archivo a Dropbox con soporte para archivos grandes."""
        if not self.dbx:
            logger.error("Cliente de Dropbox no inicializado.")
            return False
        
        logger.info(f"[DROPBOX] Subiendo: {remote_name}...")
        try:
            file_size = os.path.getsize(local_path)
            with open(local_path, 'rb') as f:
                if file_size <= CHUNK_SIZE:
                    self.dbx.files_upload(f.read(), f'/{remote_name}', mode=WriteMode.overwrite)
                else:
                    # Upload session para archivos grandes
                    chunk = f.read(CHUNK_SIZE)
                    upload_session_start = self.dbx.files_upload_session_start(chunk)
                    cursor = UploadSessionCursor(
                        session_id=upload_session_start.session_id, 
                        offset=len(chunk)
                    )
                    commit = CommitInfo(path=f'/{remote_name}', mode=WriteMode.overwrite)
                    
                    # Subir chunks restantes
                    while True:
                        remaining = file_size - cursor.offset
                        if remaining <= CHUNK_SIZE:
                            chunk = f.read(remaining)
                            self.dbx.files_upload_session_finish(chunk, cursor, commit)
                            break
                        else:
                            chunk = f.read(CHUNK_SIZE)
                            self.dbx.files_upload_session_append_v2(chunk, cursor)
                            cursor.offset += len(chunk)
            
            logger.info("[DROPBOX] Archivo subido correctamente.")
            return True
        except ApiError:
            logger.exception("Error en la API de Dropbox:")
            return False
        except Exception:
            logger.exception("Error inesperado al subir:")
            return False
        finally:
            # Limpiar archivo local
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
        return False
    
    def delete_file(self, file_name: str) -> bool:
        """Elimina un archivo de Dropbox."""
        if not self.dbx:
            logger.error("Cliente de Dropbox no inicializado.")
            return False
        
        logger.info(f"[DROPBOX] Eliminando: {file_name}...")
        try:
            self.dbx.files_delete_v2(f'/{file_name}')
            return True
        except Exception:
            logger.exception("Error al eliminar archivo:")
            return False
    
    def upload_files(self, file_paths: list[str]) -> bool:
        """Sube archivos en paralelo a Dropbox."""
        if not file_paths:
            return True
        logger.info(f"[DROPBOX] Iniciando subida paralela de {len(file_paths)} archivos...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda p: self.upload_file(p, os.path.basename(p)), file_paths))
        return all(results)

    def get_provider_name(self) -> str:
        return "Dropbox"


# ==========================================
# PROVEEDOR DE GOOGLE DRIVE
# ==========================================
class GoogleDriveProvider(StorageProvider):
    """Implementación de StorageProvider para Google Drive."""
    
    # Scopes necesarios para Google Drive API
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    
    def __init__(self):
        self.service: Any = None
        self.credentials: Any = None
        self.folder_id: str = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "root")
        self.folder_name: str = os.environ.get("GOOGLE_DRIVE_FOLDER", "")
        self.session = requests.Session()
    
    def connect(self) -> bool:
        """Inicializa el cliente de Google Drive."""
        try:
            client_id = os.environ["GOOGLE_DRIVE_CLIENT_ID"]
            client_secret = os.environ["GOOGLE_DRIVE_CLIENT_SECRET"]
            refresh_token = os.environ["GOOGLE_DRIVE_REFRESH_TOKEN"]
        except KeyError as e:
            logger.error(f"Error: La variable de entorno {e} no está configurada.")
            return False
        
        try:
            from google.oauth2.credentials import Credentials  # pyre-ignore[21]
            from googleapiclient.discovery import build  # pyre-ignore[21]
            
            self.credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                token_uri="https://oauth2.googleapis.com/token"
            )
            
            self.service = build('drive', 'v3', credentials=self.credentials)
            logger.info("[GOOGLE DRIVE] Cliente inicializado correctamente.")
            
            # Resolver folder_id si se especificó folder_name pero no folder_id directamente
            if self.folder_name and self.folder_id == "root":
                self._resolve_folder_id()
                
            return True
        except ImportError:
            logger.error("Error: No se encontró la librería google-api-python-client. Instálala con: pip install google-api-python-client google-auth-httplib2")
            return False
        except Exception:
            logger.exception("Error al inicializar el cliente de Google Drive:")
            return False
            
    def _resolve_folder_id(self) -> None:
        """Busca la carpeta por nombre o la crea si no existe, actualizando self.folder_id"""
        if not self.service or not self.folder_name:
            return
            
        try:
            # Buscar carpeta existente
            query = f"name='{self.folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                pageSize=1,
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                self.folder_id = files[0]['id']
                logger.info(f"[GOOGLE DRIVE] Carpeta existente encontrada: '{self.folder_name}' (ID: {self.folder_id})")
            else:
                # Crear la carpeta
                logger.info(f"[GOOGLE DRIVE] Creando nueva carpeta: '{self.folder_name}'")
                file_metadata = {
                    'name': self.folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = self.service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                
                self.folder_id = folder.get('id')
                logger.info(f"[GOOGLE DRIVE] Carpeta creada (ID: {self.folder_id})")
                
        except Exception:
            logger.exception(f"Error al resolver o crear la carpeta '{self.folder_name}':")
            # Fallback a root si falla
            self.folder_id = "root"
    
    def list_files(self) -> set[str]:
        """Lista archivos en Google Drive (raíz)."""
        if not self.service:
            logger.error("Cliente de Google Drive no inicializado.")
            return set()
        
        try:
            query = f"'{self.folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="files(name)"
            ).execute()
            
            files = {item['name'] for item in results.get('files', [])}
            return files
        except Exception:
            logger.exception("Error al listar archivos en Google Drive:")
            return set()
    
    def upload_file(self, local_path: str, remote_name: str) -> bool:
        """Sube un archivo a Google Drive."""
        if not self.service:
            logger.error("Cliente de Google Drive no inicializado.")
            return False
        
        logger.info(f"[GOOGLE DRIVE] Subiendo: {remote_name}...")
        try:
            from google.auth.transport.requests import Request  # pyre-ignore[21]
            
            # Asegurar token fresco
            self.credentials.refresh(Request())
            access_token = self.credentials.token
            
            file_size = os.path.getsize(local_path)
            
            # 1. Iniciar sesión de carga resumible
            init_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/octet-stream",
                "X-Upload-Content-Length": str(file_size)
            }
            metadata = {
                "name": remote_name,
                "parents": [self.folder_id]
            }
            
            response = self.session.post(init_url, headers=headers, json=metadata, timeout=30)
            response.raise_for_status()
            upload_url = response.headers.get("Location")
            
            if not upload_url:
                logger.error("No se pudo obtener la URL de carga de Google Drive.")
                return False
                
            # 2. Subir en chunks
            with open(local_path, "rb") as f:
                offset = 0
                while offset < file_size:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    chunk_len = len(chunk)
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Range": f"bytes {offset}-{offset + chunk_len - 1}/{file_size}",
                        "Content-Length": str(chunk_len)
                    }
                    
                    # PUT del chunk
                    chunk_response = self.session.put(upload_url, headers=headers, data=chunk, timeout=300)
                    
                    if chunk_response.status_code in [200, 201]:
                        # Carga finalizada con éxito
                        break
                    elif chunk_response.status_code == 308:
                        # Carga parcial, siguiente chunk
                        offset += chunk_len
                    else:
                        chunk_response.raise_for_status()
            
            logger.info(f"[GOOGLE DRIVE] Archivo subido correctamente.")
            
            # Limpiar archivo local
            try:
                os.remove(local_path)
            except OSError:
                pass
                
            return True
            
        except Exception:
            logger.exception("Error al subir archivo con el motor Requests:")
            # Limpiar archivo local también en caso de error
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except OSError:
                pass
            return False
    
    def delete_file(self, file_name: str) -> bool:
        """Elimina un archivo de Google Drive."""
        if not self.service:
            logger.error("Cliente de Google Drive no inicializado.")
            return False
        
        logger.info(f"[GOOGLE DRIVE] Eliminando: {file_name}...")
        try:
            # Buscar el archivo por nombre dentro de la carpeta configurada
            query = f"name='{file_name}' and '{self.folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                pageSize=10,
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            if not files:
                logger.warning(f"[GOOGLE DRIVE] Archivo no encontrado: {file_name}")
                return False
            
            # Eliminar el primer archivo encontrado
            file_id = files[0]['id']
            self.service.files().delete(fileId=file_id).execute()
            
            logger.info(f"[GOOGLE DRIVE] Archivo eliminado: {file_name}")
            return True
        except Exception:
            logger.exception("Error al eliminar archivo de Google Drive:")
            return False
    
    def upload_files(self, file_paths: list[str]) -> bool:
        """Sube archivos en paralelo a Google Drive."""
        if not file_paths:
            return True
        logger.info(f"[GDRIVE] Iniciando subida paralela de {len(file_paths)} archivos...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda p: self.upload_file(p, os.path.basename(p)), file_paths))
        return all(results)

    def get_provider_name(self) -> str:
        return "Google Drive"


# ==========================================
# PROVEEDOR DE RCLONE (OPTIMIZADO)
# ==========================================
class RcloneProvider(StorageProvider):
    """Implementación de StorageProvider usando Rclone para máximo rendimiento."""
    
    def __init__(self, backend_type: str):
        self.backend_type = backend_type # "googledrive" o "dropbox"
        self.folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "root")
        self.folder_name = os.environ.get("GOOGLE_DRIVE_FOLDER", "")
        self.service = None # Para resolución de carpeta si es necesario
        
    def connect(self) -> bool:
        """Verifica si rclone está instalado y resuelve carpeta."""
        try:
            subprocess.run(["rclone", "--version"], capture_output=True, check=True)
            logger.info("[RCLONE] Motor detectado y listo.")
            
            # Si es Google Drive y tenemos nombre pero no ID, intentamos resolverlo
            # Reutilizamos la lógica de GoogleDriveProvider para consistencia
            if self.backend_type == "googledrive" and self.folder_name and self.folder_id == "root":
                self._resolve_folder_id_for_rclone()
                
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("[RCLONE] Error: rclone no está instalado o no se encuentra en el PATH.")
            return False

    def _resolve_folder_id_for_rclone(self) -> None:
        """Usa un cliente temporal de Google Drive para encontrar el ID de la carpeta."""
        try:
            from google.oauth2.credentials import Credentials # pyre-ignore[21]
            from googleapiclient.discovery import build # pyre-ignore[21]
            
            creds = Credentials(
                token=None,
                refresh_token=os.environ["GOOGLE_DRIVE_REFRESH_TOKEN"],
                client_id=os.environ["GOOGLE_DRIVE_CLIENT_ID"],
                client_secret=os.environ["GOOGLE_DRIVE_CLIENT_SECRET"],
                token_uri="https://oauth2.googleapis.com/token"
            )
            service = build('drive', 'v3', credentials=creds)
            query = f"name='{self.folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = service.files().list(q=query, pageSize=1, fields="files(id)").execute()
            files = results.get('files', [])
            if files:
                self.folder_id = files[0]['id']
                logger.info(f"[RCLONE] Carpeta resuelta: {self.folder_name} -> {self.folder_id}")
        except Exception:
            logger.warning(f"[RCLONE] No se pudo resolver la carpeta '{self.folder_name}', se usará la raíz.")

    def list_files(self) -> set[str]:
        """Lista archivos usando rclone ls."""
        # Para simplificar y evitar configuraciones complejas de listado, 
        # delegamos el listado inicial a los proveedores nativos si es necesario,
        # o implementamos un listado básico con rclone si el usuario lo requiere.
        # Por ahora, PESync usa este set para saber qué falta, así que implementamos rclone lsf.
        
        backend_cmd = self._get_backend_prefix()
        cmd = ["rclone", "lsf", backend_cmd] + self._get_auth_flags()
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            files = {line.strip() for line in result.stdout.splitlines() if line.strip()}
            return files
        except Exception:
            logger.exception("[RCLONE] Error al listar archivos:")
            return set()

    def upload_file(self, local_path: str, remote_name: str) -> bool:
        """Sube un archivo usando rclone copyto."""
        backend_cmd = f"{self._get_backend_prefix()}{remote_name}"
        
        # rclone copyto <local> <remote>:<path>
        cmd = [
            "rclone", "copyto", 
            local_path, 
            backend_cmd,
            "--progress"
        ] + self._get_auth_flags()
        
        logger.info(f"[RCLONE] Subiendo con motor de alto rendimiento: {remote_name}...")
        try:
            # Ejecutamos de forma que se vea el progreso en la consola
            subprocess.run(cmd, check=True)
            logger.info(f"[RCLONE] Subida completada: {remote_name}")
            
            # Limpiar local tras subida exitosa (consistente con otros proveedores)
            if os.path.exists(local_path):
                os.remove(local_path)
            return True
        except Exception:
            logger.exception(f"[RCLONE] Error crítico durante la subida de {remote_name}:")
            return False

    def upload_files(self, file_paths: list[str]) -> bool:
        """Sube múltiples archivos usando rclone copy sobre el directorio contenedor."""
        if not file_paths:
            return True
            
        # Obtenemos el directorio donde están los archivos (asumimos que están en el mismo)
        temp_dir = os.path.dirname(file_paths[0])
        
        # rclone copy <dir> <remote>:
        # --transfers 4 permite subir 4 archivos simultáneamente
        cmd = [
            "rclone", "copy", 
            temp_dir, 
            self._get_backend_prefix(),
            "--transfers", "4",
            "--progress"
        ] + self._get_auth_flags()
        
        logger.info(f"[RCLONE] Iniciando subida masiva de {len(file_paths)} archivos...")
        try:
            subprocess.run(cmd, check=True)
            logger.info("[RCLONE] Subida masiva completada.")
            
            # Limpiar archivos locales tras subida exitosa
            for p in file_paths:
                if os.path.exists(p):
                    os.remove(p)
            return True
        except Exception:
            logger.exception("[RCLONE] Error crítico durante la subida masiva:")
            return False

    def delete_file(self, file_name: str) -> bool:
        """Elimina un archivo usando rclone deletefile."""
        backend_cmd = f"{self._get_backend_prefix()}{file_name}"
        cmd = ["rclone", "deletefile", backend_cmd] + self._get_auth_flags()
        
        try:
            subprocess.run(cmd, check=True)
            return True
        except Exception:
            logger.exception(f"[RCLONE] Error al eliminar {file_name}:")
            return False

    def get_provider_name(self) -> str:
        return f"Rclone ({self.backend_type})"

    def _get_backend_prefix(self) -> str:
        if self.backend_type == "googledrive":
            # Nota importante: no usar comillas simples aquí, rclone/subprocess las toma literalmente
            return f":drive,root_folder_id={self.folder_id}:"
        return ":dropbox:"

    def _get_auth_flags(self) -> list[str]:
        """Genera los flags de autenticación 'on-the-fly' para rclone."""
        flags = []
        if self.backend_type == "googledrive":
            token_json = json.dumps({"refresh_token": os.environ["GOOGLE_DRIVE_REFRESH_TOKEN"]})
            flags = [
                "--drive-client-id", os.environ["GOOGLE_DRIVE_CLIENT_ID"],
                "--drive-client-secret", os.environ["GOOGLE_DRIVE_CLIENT_SECRET"],
                "--drive-token", token_json
            ]
        elif self.backend_type == "dropbox":
            # Para Dropbox rclone prefiere el token en este formato si es refresh token
            token_json = json.dumps({"refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"]})
            flags = [
                "--dropbox-client-id", os.environ["DROPBOX_APP_KEY"],
                "--dropbox-client-secret", os.environ["DROPBOX_APP_SECRET"],
                "--dropbox-token", token_json
            ]
        return flags


# ==========================================
# FÁBRICA DE PROVEEDORES
# ==========================================
def get_storage_provider() -> StorageProvider | None:
    """
    Retorna el proveedor de almacenamiento configurado mediante la variable de entorno STORAGE_PROVIDER.
    
    Valores posibles:
    - "dropbox" -> DropboxProvider
    - "googledrive" -> GoogleDriveProvider
    
    Por defecto retorna DropboxProvider si no se especifica.
    """
    provider = os.environ.get("STORAGE_PROVIDER", "dropbox").lower()
    use_rclone = os.environ.get("USE_RCLONE", "false").lower() == "true"
    
    if use_rclone:
        if provider in ["googledrive", "dropbox"]:
            return RcloneProvider(provider)
        else:
            logger.warning(f"Rclone no soporta el proveedor '{provider}'. Usando motor nativo.")

    if provider == "googledrive":
        return GoogleDriveProvider()
    elif provider == "dropbox":
        return DropboxProvider()
    else:
        logger.warning(f"Proveedor desconocido '{provider}'. Usando Dropbox por defecto.")
        return DropboxProvider()


# ==========================================
# COMPATIBILIDAD CON main.py (DEPRECATED)
# ==========================================
# Funciones de compatibilidad para mantener compatibilidad con código existente
def get_dropbox_client():
    """Función de compatibilidad para main.py. Usa el nuevo sistema de abstracción."""
    provider = DropboxProvider()
    if provider.connect():
        return provider.dbx
    return None


def get_google_drive_client():
    """Función de compatibilidad para obtener cliente de Google Drive."""
    provider = GoogleDriveProvider()
    if provider.connect():
        return provider.service
    return None
