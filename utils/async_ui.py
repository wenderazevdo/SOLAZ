"""Consultas ao banco / trabalhos lentos fora da thread da interface.

O Tkinter só pode ser mexido na thread principal; por isso o trabalho pesado
roda numa thread e o resultado volta pela fila do `after`, sem congelar a tela:

    rodar_em_segundo_plano(
        self,                                  # qualquer widget da tela
        lambda: self.dao.listar(),             # roda em outra thread (só leitura/consulta!)
        lambda linhas: self._preencher(linhas) # roda na thread da UI com o resultado
    )

Se a tela for fechada (ou o usuário trocar de tela e você passar `valido`),
o resultado é descartado em vez de ser aplicado em widgets que não existem mais.
"""
import logging
import sys
import threading

log = logging.getLogger("solaz")


def rodar_em_segundo_plano(widget, trabalho, ao_concluir, ao_erro=None, valido=None):
    """`trabalho()` -> resultado (thread de fundo); `ao_concluir(resultado)` na UI.
    `ao_erro(exc)` é opcional; sem ele o erro vai para o tratador global do app.
    `valido()` (opcional) é checado antes de aplicar o resultado."""

    def entregar(fn):
        try:
            widget.after(0, fn)
        except Exception:        # widget/janela já destruídos
            pass

    def worker():
        try:
            resultado = trabalho()
        except Exception as exc:
            info = sys.exc_info()
            log.warning("Falha em consulta em segundo plano", exc_info=info)

            def falhou():
                if ao_erro is not None:
                    ao_erro(exc)
                else:
                    widget.report_callback_exception(*info)   # diálogo/log padrão do app
            entregar(falhou)
            return

        def concluir():
            if valido is not None and not valido():
                return
            try:
                if not widget.winfo_exists():
                    return
            except Exception:
                return
            ao_concluir(resultado)
        entregar(concluir)

    threading.Thread(target=worker, daemon=True, name="consulta-bg").start()
