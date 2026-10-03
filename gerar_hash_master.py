"""
Gera o hash da Senha Mestra da conta de desenvolvedor (dev_master).

Rode uma vez:  python gerar_hash_master.py
Cole o resultado em config.py (MASTER_SENHA_HASH) ou defina a variável de
ambiente SOLAZ_MASTER_HASH com o valor gerado. Enquanto MASTER_SENHA_HASH
estiver vazio, a conta dev_master fica desativada — ninguém consegue
logar com ela, nem por engano.
"""
import getpass

from models.usuario_dao import hash_senha_com_salt_embutido


def main():
    print("Geração do hash da Senha Mestra (dev_master)")
    print("-" * 50)
    senha = getpass.getpass("Digite a nova senha mestra: ")
    confirmacao = getpass.getpass("Confirme a senha mestra: ")

    if not senha:
        print("Senha vazia — cancelado.")
        return
    if senha != confirmacao:
        print("As senhas não conferem — cancelado.")
        return

    hash_gerado = hash_senha_com_salt_embutido(senha)
    print("\nHash gerado com sucesso. Cole em config.py:\n")
    print(f'MASTER_SENHA_HASH = "{hash_gerado}"')
    print("\n...ou defina como variável de ambiente:")
    print(f'  set SOLAZ_MASTER_HASH={hash_gerado}      (Windows, cmd)')
    print(f'  $env:SOLAZ_MASTER_HASH="{hash_gerado}"   (Windows, PowerShell)')


if __name__ == "__main__":
    main()
