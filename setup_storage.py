# pyre-ignore-all-errors[21]
import requests
import webbrowser

def main():
    print("=" * 60)
    print("Bienvenido al Asistente de Configuración de Almacenamiento")
    print("=" * 60)
    print("\nPara automatizar la subida, necesitamos crear un Token de Acceso Persistente (Refresh Token).")
    print("Sigue estos sencillos pasos:\n")
    print("1. Ve a https://www.dropbox.com/developers/apps")
    print("2. Haz clic en 'Create app'.")
    print("3. Selecciona 'Scoped access' y 'App folder' (o 'Full Dropbox'). Ponle un nombre a tu app.")
    print("4. Ve a la pestaña 'Permissions' de tu nueva App, marca 'files.content.write' y dale a 'Submit' abajo.")
    print("5. Vuelve a la pestaña 'Settings' y copia el 'App key' y el 'App secret'.")
    print("-" * 60)
    
    app_key = input("Pega aquí tu 'App key': ").strip()
    app_secret = input("Pega aquí tu 'App secret': ").strip()
    
    if not app_key or not app_secret:
        print("Error: Necesitas ingresar ambos valores.")
        return

    # Construir la URL de autorización
    auth_url = f"https://www.dropbox.com/oauth2/authorize?client_id={app_key}&response_type=code&token_access_type=offline"
    
    print("\n" + "-" * 60)
    print("Paso 6: Ahora debes autorizar a tu propia App para que acceda a tu Dropbox.")
    print("Se abrirá una ventana en tu navegador web. Inicia sesión, dale a 'Permitir',")
    print("y copia el 'Access Code' (Código de acceso corporativo) que te dará la página.")
    print(f"(Si el navegador no se abre automáticamente, entra aquí: {auth_url} )")
    print("-" * 60)
    
    # Intentar abrir el navegador automáticamente
    try:
        webbrowser.open_new(auth_url)
    except Exception:
        pass
        
    auth_code = input("\nPega aquí tu 'Access Code': ").strip()
    
    if not auth_code:
        print("Error: Necesitas el código de acceso.")
        return
        
    print("\nObteniendo el Refresh Token...")
    
    # Hacer la petición para cambiar el code por un refresh_token
    response = requests.post("https://api.dropbox.com/oauth2/token", data={
        "code": auth_code,
        "grant_type": "authorization_code",
    }, auth=(app_key, app_secret))
    
    if response.status_code == 200:
        data = response.json()
        refresh_token = data.get("refresh_token")
        
        print("\n" + "=" * 60)
        print("¡ÉXITO! Aquí están los 3 Secretos que debes guardar en GitHub:")
        print("Ve a Settings > Secrets and variables > Actions y crea estos 3 New repository secrets:\n")
        
        print(f"1) Nombre: DROPBOX_APP_KEY")
        print(f"   Valor:  {app_key}\n")
        
        print(f"2) Nombre: DROPBOX_APP_SECRET")
        print(f"   Valor:  {app_secret}\n")
        
        print(f"3) Nombre: DROPBOX_REFRESH_TOKEN")
        print(f"   Valor:  {refresh_token}\n")
        print("=" * 60)
        
        # Intentar escribir automáticamente en .env
        try:
            with open(".env", "w", encoding="utf-8") as env_file:
                env_file.write(f"DROPBOX_APP_KEY={app_key}\n")
                env_file.write(f"DROPBOX_APP_SECRET={app_secret}\n")
                env_file.write(f"DROPBOX_REFRESH_TOKEN={refresh_token}\n")
            print("✅ El archivo .env ha sido actualizado automáticamente.")
        except Exception as e:
            print(f"⚠️ No se pudo escribir el archivo .env: {e}")
            print("Por favor, copia los valores manualmente.")
            
        print("\n¡Una vez los configures, empuja los archivos a GitHub y corre el Action!")
    else:
        print(f"\nError al obtener el token. Código: {response.status_code}")
        print(response.text)
    
    input("\nPresiona ENTER para cerrar esta ventana...")

if __name__ == "__main__":
    main()
