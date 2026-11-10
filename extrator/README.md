# Correções do Extrator PEC e-SUS 1.0.0 (módulo Filhos de Minas)

O Extrator PEC e-SUS é da SES-MG (licença MIT, `"author": "Equipe Extrator PEC e-SUS"`), distribuído em
<https://atualizacoes-extrator-pec-esus.saude.mg.gov.br>. Este diretório **não** redistribui o extrator: traz só um
`diff` sobre a versão 1.0.0 com quatro correções encontradas em produção em Ipatinga (2026), e um aplicador.

| # | Correção | Problema que resolve |
|---|---|---|
| 1 | **CNS do cadastro do cidadão** | A 1.0.0 lê o CNS só do atendimento; a API da SES-MG exige CNS e recusava com erro 500 (`null value in column cns`) gestantes que tinham CNS no cadastro. Passa a buscar também em `tb_cidadao` e `tb_fat_cidadao_pec`, aceita CPF **ou** CNS e repara os itens já gravados. |
| 2 | **Releitura de todos os pendentes** | Gestante corrigida na UBS podia levar horas (ou nunca) para ser relida: a releitura pegava 500 itens aleatórios por hora e só com DUM recente. Passa a reler todos os pendentes sem CPF/CNS a cada execução. |
| 3 | **Fora do recorte** | Atendimento com DUM há mais de 365 dias ficava na fila para sempre, reenviado toda hora. Passa a ser marcado `status_response = 'fora_recorte'` e não é enviado; DUM corrigida no PEC devolve o item à fila. |
| 4 | **Cadência de reenvio** | Recusa por Bolsa Família (regra do programa, não erro) era reenviada toda hora. Passa a 1 vez por dia; a rodada das 03h relê os itens fora do recorte. |

Resultado em Ipatinga: rodada de 29 para 13 minutos e de 5.710 para cerca de 1.300 envios por hora, sem perder gestante.

## Aplicar

O instalador (`instalar.sh`, com `EXTRATOR_CORRECOES=1`) faz isso sozinho. À mão, depois do `npm i -g extrator-pec-esus-1.0.0.tgz`:

```bash
./aplicar-correcoes.sh            # descobre a pasta do pacote pelo `node` do PATH; idempotente
```

Numa versão nova da SES-MG, confira primeiro se ela já traz as correções (`grep -n nu_cns modules/filhos_de_minas/index.js`
no pacote: se o CNS vier só de `a.nu_cns`, não traz). O aplicador recusa versão diferente da 1.0.0 — nesse caso, leia o
`diff` e adapte. `update-core` ou reinstalar o pacote oficial desfaz as correções.

## Conferir

```bash
grep -c 'CORRECAO CNS' $(npm root -g)/extrator-pec-esus/app/core/storage.js          # 1
grep -c 'fora_recorte' $(npm root -g)/extrator-pec-esus/modules/filhos_de_minas/sender.js   # > 0
```
