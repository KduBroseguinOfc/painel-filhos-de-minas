-- Papel SOMENTE LEITURA do Painel Filhos de Minas no PostgreSQL do PEC e-SUS (banco esus).
-- Rodar como superusuario do PostgreSQL, passando a senha como variavel do psql (nunca no arquivo):
--   psql -h <host> -p <porta> -U postgres -d esus -v senha='<senha gerada>' -f dw-papel-somente-leitura.sql
-- Idempotente: cria o papel se nao existir e (re)define a senha. So SELECT nas tabelas que a coleta le (fm/coleta.py).
SELECT format('CREATE ROLE painelfm_ro LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 3', :'senha')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'painelfm_ro') \gexec
ALTER ROLE painelfm_ro PASSWORD :'senha';
ALTER ROLE painelfm_ro SET default_transaction_read_only = on;
ALTER ROLE painelfm_ro SET statement_timeout = '120s';
GRANT CONNECT ON DATABASE esus TO painelfm_ro;
GRANT USAGE ON SCHEMA public TO painelfm_ro;
-- 23 tabelas (atendimentos, cadastros CDS para o endereco, dimensoes, procedimentos/exames do pre-natal, vacinacao)
GRANT SELECT ON tb_cds_cad_domiciliar, tb_cds_cad_individual, tb_cds_domicilio_familia, tb_cidadao, tb_dim_ciap, tb_dim_cid, tb_dim_dose_imunobiologico, tb_dim_equipe, tb_dim_imunobiologico, tb_dim_procedimento, tb_dim_profissional, tb_dim_tempo, tb_dim_tipo_logradouro, tb_dim_unidade_saude, tb_fat_atd_ind_problemas, tb_fat_atd_ind_procedimentos, tb_fat_atendimento_individual, tb_fat_cidadao_pec, tb_fat_rel_op_gestante, tb_fat_vacinacao, tb_fat_vacinacao_vacina, tb_localidade, tb_unidade_saude TO painelfm_ro;
-- Teste (com o proprio papel): SELECT count(*) FROM tb_dim_unidade_saude;   -> numero de unidades
--                              SELECT count(*) FROM tb_fat_atd_ind_problemas; -> permission denied (esperado)
-- pg_hba.conf do servidor do banco: liberar painelfm_ro so a partir do IP do painel, por exemplo
--   host  esus  painelfm_ro  <ip-do-painel>/32  scram-sha-256     (PostgreSQL 9.6: md5)
