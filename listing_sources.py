"""
Conectores plugáveis de ingestão de anúncios de listagem (item 1).

[Sobre "webhooks dedicados"] Pesquisei antes de implementar: nenhuma exchange
Tier-2/3 relevante (MEXC, Gate.io, Bitget, KuCoin, LBank, BingX) oferece
webhook público de anúncios — isso normalmente só existe como integração
privada de parceria (market maker, provedor de liquidez), não como algo que
um usuário de varejo consegue assinar. O que existe de verdade, verificado ao
vivo nesta sessão, é a API REST pública de anúncios da MEXC
(`GET https://api.mexc.com/api/v3/announcements`, sem autenticação, limite
de 5 requisições/2s). Por isso a arquitetura é polling de altíssima
frequência (respeitando o rate limit real de cada exchange), com a MESMA
interface plugável (`AnnouncementSource`) que um webhook usaria se algum dia
uma exchange oferecer um — o resto do sistema (extrator, motor de execução,
persistência) não muda nada se a fonte virar push em vez de pull.

Para adicionar uma exchange nova: criar uma subclasse de AnnouncementSource
com sua própria lógica de fetch_latest() e registrar em SOURCE_REGISTRY. Se
a exchange não tiver API de anúncios pública (a maioria não tem), a fonte
pode ser implementada como scraping da página de anúncios — mais frágil
(sujeito a mudança de HTML) e deve ser tratado como tal no polling (falhas
soft, nunca derrubar o loop).
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger("ListingSources")


@dataclass
class Announcement:
    exchange: str
    title: str
    url: str
    published_at_ms: int
    raw: dict


class AnnouncementSource:
    exchange_key: str = None
    display_name: str = None
    poll_interval_seconds: float = 2.0

    async def fetch_latest(self, session) -> list[Announcement]:
        """Retorna os anúncios mais recentes, do mais novo pro mais antigo.
        Nunca deve levantar exceção pro chamador — erros de rede devem ser
        engolidos e retornar lista vazia (o loop de polling trata isso como
        'nada de novo agora', não como falha fatal)."""
        raise NotImplementedError


class MexcAnnouncementSource(AnnouncementSource):
    """
    [VERIFICADO AO VIVO nesta sessão] Endpoint público real, sem autenticação:
    GET https://api.mexc.com/api/v3/announcements?language=en-US&page=1&limit=20
    Rate limit documentado: 5 requisições / 2 segundos. poll_interval_seconds
    fica com margem de segurança sobre isso (1 req/s = bem dentro do limite).

    Testado contra uma amostra real de 50 anúncios: a maioria NÃO é listagem
    nova (deslistagem, futures, funding rate, promoções) — é o
    ticker_extractor.py que faz essa triagem, não esta fonte.
    """
    exchange_key = "MEXC"
    display_name = "MEXC"
    poll_interval_seconds = 1.0
    ANNOUNCEMENTS_URL = "https://api.mexc.com/api/v3/announcements"

    async def fetch_latest(self, session) -> list[Announcement]:
        try:
            params = {"language": "en-US", "page": 1, "limit": 20}
            async with session.get(self.ANNOUNCEMENTS_URL, params=params, timeout=2.0) as resp:
                if resp.status != 200:
                    logger.warning(f"[MEXC] Anúncios retornou HTTP {resp.status}")
                    return []
                data = await resp.json()
                details = (data.get("data") or [{}])[0].get("details") or []
                return [
                    Announcement(
                        exchange=self.exchange_key,
                        title=d.get("title", ""),
                        url=d.get("url", ""),
                        published_at_ms=int(d.get("postTime") or 0),
                        raw=d,
                    )
                    for d in details
                ]
        except Exception as e:
            logger.debug(f"[MEXC] Falha ao buscar anúncios (tolerado, tenta de novo no próximo ciclo): {e}")
            return []


SOURCE_REGISTRY = {
    "MEXC": MexcAnnouncementSource,
}


def create_source(exchange_key: str) -> AnnouncementSource:
    SourceClass = SOURCE_REGISTRY.get(exchange_key.upper())
    if SourceClass is None:
        raise ValueError(
            f"Fonte de anúncios para '{exchange_key}' não implementada. "
            f"Disponíveis: {list(SOURCE_REGISTRY.keys())}. "
            f"Para adicionar: verificar se a exchange tem API pública de "
            f"anúncios (a maioria não tem) e implementar uma subclasse de "
            f"AnnouncementSource seguindo o padrão de MexcAnnouncementSource."
        )
    return SourceClass()
