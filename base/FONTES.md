# Base documental do DrenaAssist

**Corte da base:** 19/11/2026. **Formato indexado:** `chunks.jsonl`, UTF-8, um objeto JSON por linha. São **9 documentos e 41 trechos**. Os textos dos trechos são paráfrases originais em português dos pontos indicados pelas URLs; os documentos completos permanecem em seus sites de origem.

| Documento | Fonte e formato original | Condição de reutilização adotada | Trechos |
|---|---|---|---:|
| [EPA-OM](https://www.epa.gov/npdes/stormwater-maintenance) | EPA, página HTML sobre manutenção de drenagem pluvial | Paráfrase e atribuição; elementos de terceiros na página podem ter direitos próprios | 4 |
| [EPA-CB](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=200044BA.TXT) | EPA, ficha técnica TXT, EPA 832-F-99-011 | Paráfrase e atribuição; publicação federal | 6 |
| [EPA-PM](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=200044A0.TXT) | EPA, ficha técnica TXT, EPA 832-F-99-004 | Paráfrase e atribuição; publicação federal | 5 |
| [EPA-SWPPP](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P1011EAT.TXT) | EPA, guia TXT de 2021 para operadores industriais | Paráfrase e atribuição; publicação federal | 6 |
| [EPA-LIFT](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=901U0X00.TXT) | EPA, ficha técnica TXT sobre estação elevatória de esgoto | Paráfrase e atribuição; publicação federal | 5 |
| [OSHA-FLOOD](https://www.osha.gov/flood/response) | OSHA, página HTML de segurança na resposta a inundações | Paráfrase e atribuição; orientação de agência federal | 5 |
| [NWS-BEFORE](https://www.weather.gov/safety/flood-before) | NOAA/NWS, página HTML de preparação | [Domínio público, salvo indicação contrária](https://www.weather.gov/disclaimer); sem alegar endosso oficial; paráfrase identificada | 3 |
| [NWS-DURING](https://www.weather.gov/safety/flood-during) | NOAA/NWS, página HTML de segurança durante inundação | [Domínio público, salvo indicação contrária](https://www.weather.gov/disclaimer); sem alegar endosso oficial; paráfrase identificada | 3 |
| [EPA-CHECK](https://www.epa.gov/sites/production/files/2015-11/documents/guidance_document.pdf) | Erie County Department of Environment and Planning, PDF de 39 páginas hospedado pela EPA | Titularidade integral não confirmada; somente fatos resumidos em paráfrase; PDF não redistribuído | 4 |

## Seleção e rastreabilidade

Cada trecho tem `chunk_id`, `document_id`, `title`, `source`, `url`, `text`, `license` e `accessed_at`. O identificador combina o documento e um número sequencial. A fonte EPA-CHECK foi corretamente atribuída a Erie County, conforme a capa do PDF, e não à EPA apenas por estar hospedada em seu domínio.

Os assuntos cobertos são: plano de manutenção, limpeza de ralos e caixas de captação, grelhas e canaletas, inspeção de bombas, sinais de obstrução e contaminação, relatórios de inspeção, preparação antes de chuva e segurança em alagamentos. As fichas da EPA para instalações industriais e estações de esgoto descrevem seus próprios contextos; os trechos não transformam recomendações norte-americanas em normas brasileiras nem em especificações da instalação monitorada.

As páginas foram abertas e seus pontos verificados em 19/11/2026. Links e conteúdos externos podem mudar. As condições de reutilização descritas aqui justificam o emprego de paráfrases e links, sem incluir os PDFs ou páginas originais no repositório.
