# IRIS Vector Management: desenvolvimento de um portal de vetores com Embedded Python, SQL e ObjectScript

## Introdução

O **IRIS Vector Management** é um portal hospedado pelo InterSystems IRIS para inspecionar e preencher colunas vetoriais. A aplicação descobre propriedades `VECTOR` e `EMBEDDING`, exibe registros e prévias limitadas dos vetores, executa buscas por similaridade, resolve a localização do storage, valida e cria índices HNSW e publica tarefas de geração para tabelas existentes.

A implementação usa Embedded Python, SQL vetorial, o dicionário de classes compiladas, globals do IRIS, Task Manager e SysAdmin API v2. HTML, CSS e JavaScript formam a interface servida por `%SYS.Python.WSGI`.

O ambiente de referência é o **InterSystems IRIS Community 2026.2, Build 221U**, fixado por digest no `Dockerfile`. A aplicação verifica esse build antes de habilitar o catálogo, a busca vetorial e a manutenção de HNSW. O comportamento validado tem esse release como alvo.

As seções a seguir acompanham a implementação desde o navegador até o SQL e a execução pelo agendador. O exemplo prático preenche os vetores dos documentos, altera os dados de origem e usa a mesma tarefa para processar documentos novos e alterados.

## 1. Arquitetura: a aplicação executa dentro do IRIS

O navegador abre `/vector-admin/`. A aplicação web do IRIS despacha as requisições para `%SYS.Python.WSGI`, que carrega `wsgi.application` e, em seguida, `vector_admin/app.py`.

O processo WSGI executa SQL e acessa classes IRIS pelo módulo `iris`. Um cliente HTTP local trata as chamadas à SysAdmin API com as credenciais do operador da requisição. A criação de HNSW roda em um `JOB`; a geração de vetores roda como tarefa do Task Manager do IRIS.

![Arquitetura da aplicação](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/diagrams/pt-br/01-architecture.png)

O IRIS executa a consulta de similaridade e a função SQL `EMBEDDING`. O navegador recebe dados e evidências operacionais pelo portal.

### Da interface ao Embedded Python

O `iris/install.script` registra `/vector-admin` com `DispatchClass=%SYS.Python.WSGI`, `WSGIAppName=wsgi`, `WSGICallable=application` e `WSGIAppLocation=/usr/irissys/csp/vector-admin/`. O ponto de entrada completo em `wsgi.py` é:

```python
from vector_admin.app import application
```

O `vector_admin/static/index.html` define navegação, tabelas e formulários. O `app.css` usa Grid para formulários e cartões, Flexbox para barras de ferramentas e media queries para telas menores. O `app.js` alterna as telas pelo atributo `hidden` e atualiza os elementos do DOM após cada requisição. O editor Python define `aria-invalid` e apresenta os resultados da validação em um elemento de status.

A função de requisição do navegador, reformatada de `app.js`, envia JSON para a mesma origem e inclui o token CSRF retornado por `/api/capabilities`:

```javascript
async function api(path, body) {
    const response = await fetch(path, {
        credentials: 'same-origin',
        headers: body ? {
            'Content-Type': 'application/json',
            'X-CSRF-Token': state.cap?.csrf || ''
        } : {},
        method: body ? 'POST' : 'GET',
        body: body ? JSON.stringify(body) : undefined
    });
    const data = await response.json();
    if (!response.ok) throw new Error(`${data.code}: ${data.message}`);
    return data;
}
```

Em uma busca, o formulário envia `{vector: [1, 0, 0], distance: 'Cosine', k: 3}` para `api/vectors/<asset-id>/search`. O identificador vem da resposta do inventário. A rota de vetores em `app.py` resolve esse identificador pelo catálogo, entra no namespace do ativo e encaminha a requisição. Este trecho mostra o tratamento da busca:

```python
asset = catalog.lookup(match[1])
suffix = match[2]
with namespace(asset['namespace']):
    if method == 'POST' and suffix == '/search':
        return search.execute(asset, json_body(environ))
```

O gerenciador de contexto `namespace` restaura o namespace anterior em `finally`. `search.execute` retorna resultados, tempo, SQL e evidência do plano. O ponto de entrada WSGI serializa esse dicionário em JSON, e a interface apresenta os resultados. Erros da aplicação retornam `code` e `message` com um status HTTP.

### Responsabilidades no código

| Arquivo ou diretório | Responsabilidade |
| --- | --- |
| `vector_admin/app.py` | Rotas WSGI, tratamento de JSON, limites de requisição e respostas de erro. |
| `auth.py`, `settings.py`, `sql.py` | Identidade, permissões, tokens, configuração, namespaces e execução SQL. |
| `catalog.py`, `configs.py` | Descoberta de propriedades vetoriais e configurações de embedding. |
| `explorer.py`, `search.py` | Paginação de registros, prévias de vetores, buscas por similaridade e diagnóstico de planos. |
| `placement.py`, `sysadmin_client.py` | Resolução do storage e integração administrativa. |
| `indexes.py` | Validação, confirmação e execução assíncrona de DDL HNSW. |
| `recipes.py`, `generators.py`, `seed_runner.py` | Receitas, validação Python e preenchimento repetível de vetores. |
| `tasks.py`, `audit.py` | Monitoramento de tarefas e auditoria da aplicação. |
| `vector_admin/static/` | Interface HTML, CSS e JavaScript. |
| `iris/`, `tools/`, `tests/` | Classes ObjectScript, instalação, fixtures e verificações. |

Os módulos sem diretório nessa tabela pertencem a `vector_admin/`. O código usa módulos funcionais e SQL explícito, sem ORM.

## 2. Tecnologias e bibliotecas

O portal usa a biblioteca padrão do Python e o módulo `iris` fornecido pelo Embedded Python. `iris.sql.exec` executa SQL, `iris.cls` acessa classes e `iris.system` retorna informações do processo e da instância.

| Tecnologia | Uso no projeto |
| --- | --- |
| `%SYS.Python.WSGI` | Hospeda a aplicação Python dentro do IRIS. |
| `%Dictionary.CompiledClass`, `CompiledProperty`, `CompiledIndex`, `CompiledStorage` | Fornece estrutura compilada, parâmetros vetoriais, índices e definições de storage. |
| `VECTOR`, `EMBEDDING`, `TO_VECTOR`, `VECTOR_COSINE`, `VECTOR_DOT_PRODUCT` | Fornece persistência, geração e busca vetorial por SQL. |
| `%Embedding.Config`, `%Embedding.SentenceTransformers` | Fornece configuração de modelo e o provedor da demonstração. |
| `%SYS.Task.Definition` | Classe-base de `VectorAdmin.SeedTask`, executada pelo agendador do IRIS. |
| ObjectScript `JOB`, `LOCK`, transações e `%SYSTEM.Event` | Coordena workers e controla a execução entre processos. |
| `json`, `re`, `math`, `hashlib`, `hmac`, `secrets`, `contextvars`, `urllib` | Implementa serialização, validação, assinaturas, contexto da requisição e integração HTTP. |
| `ast` e `compile` | Valida sintaxe e assinatura de geradores Python. |
| HTML, CSS e JavaScript com `fetch` | Implementa a interface e as requisições de mesma origem. |
| Docker e Compose | Constrói e executa o ambiente de demonstração. |

As dependências da demonstração ficam separadas dos requisitos do portal. `requirements-seeder.txt` fixa o **Faker 37.6.0** para os documentos de exemplo em português. `requirements-fixtures.txt` fixa a pilha do modelo local, incluindo **SentenceTransformers 5.1.2**, **Transformers 4.57.6**, **PyTorch 2.14.0+cpu** e dependências numéricas e de tokenização.

`WITH_FIXTURES=0` omite as fixtures e essa pilha de aprendizado de máquina. O Dockerfile ainda instala o requisito do seeder. A aplicação web não usa Flask, Django nem etapa de build com Node.js.

## 3. Modelo de dados: vetores, embeddings e evidência de origem

### Duas representações

A fixture `VectorFixture.Raw` declara uma coluna vetorial comum:

```sql
CREATE TABLE VectorFixture.Raw (
    ID INTEGER IDENTITY,
    Label VARCHAR(80),
    Embedding VECTOR(DOUBLE,3)
)
```

A fixture insere valores com `TO_VECTOR`:

```python
iris.sql.exec(
    'INSERT INTO VectorFixture.Raw (Label,Embedding) '
    'VALUES (?,TO_VECTOR(?,DOUBLE))',
    'Fixture 1',
    '[1,0,0]'
)
```

Esse esquema registra tipo e dimensão. Ele não contém vínculo com modelo ou texto de origem. O inventário exibe origem e modelo como desconhecidos quando os metadados não comprovam essa relação.

A fixture gerenciada declara a configuração e a propriedade de origem:

```sql
CREATE TABLE VectorFixture.Managed (
    ID INTEGER IDENTITY,
    Content VARCHAR(512),
    Embedding EMBEDDING('vector-fixture-tiny','Content')
)
```

O catálogo pode associar o vetor a `Content` e `vector-fixture-tiny`. Ele lê de `%Embedding.Config` a classe do provedor, a dimensão e as configurações públicas permitidas.

Uma tarefa criada pelo portal adiciona uma coluna comum `VECTOR(DOUBLE,n)`, inclusive quando usa um modelo. A receita armazena o vínculo operacional com a origem e o gerador. A coluna continua sendo vetorial comum; o esquema não se transforma em uma propriedade `EMBEDDING` gerenciada.

![Filtros do inventário e colunas vetoriais](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/01-inventory.png)

### O catálogo lê o dicionário compilado

`catalog.discover` consulta `%Dictionary.CompiledProperty` junto com `%Dictionary.CompiledClass`. No build de referência, `INFORMATION_SCHEMA` pode expor tipos vetoriais como `varchar`; o dicionário compilado preserva sua identidade vetorial.

Os tipos reconhecidos são `%Library.Vector`, `%Embedding.Vector` e `%Library.Embedding`. O serviço lê `LEN`, `DATATYPE`, `MODEL`, `SOURCE` e `CONFIGURATION` pela API de objetos do dicionário:

```python
obj = iris.cls('%Dictionary.CompiledProperty')._OpenId(
    class_name + '||' + property_name
)
dimensions = obj.Parameters.GetAt('LEN')
element_type = obj.Parameters.GetAt('DATATYPE')
```

O catálogo também resolve o nome SQL da propriedade, uma chave utilizável, a definição de storage e índices com `TypeClass = %SQL.Index.HNSW`. Cada ativo recebe um fingerprint dos metadados e um identificador assinado vinculado ao operador. As requisições seguintes validam esse identificador e atualizam os dados do catálogo.

## 4. Modelo operacional de receitas e execuções

Os valores permanecem nas tabelas de destino. O `tools/install.py` cria o esquema `VectorAdmin` para os dados de controle da aplicação:

| Tabela | Chave | Conteúdo principal |
| --- | --- | --- |
| `VectorRecipe` | `RecipeId, Revision` | Nome, estado, payload JSON, fingerprint, autor e datas. |
| `SeedSchedule` | `TaskId` | Associação entre tarefa IRIS e receita/revisão. |
| `SeedRun` | `RunId` | Estado, contadores, última chave, heartbeat e erro resumido. |
| `SeedMetrics` | `RunId` | Vetores criados, destinos ausentes e política da execução. |
| `SeedRow` | `RecipeId, KeyHash` | Assinaturas da origem e do gerador e data de atualização. |
| `Operation` | `OperationId` | Proposta HNSW, expiração, estado e resultado. |
| `Audit` | `EventId` | Operador, ação, alvo, estado e evidências filtradas. |
| `FixtureRegistry` | `Name` | Tabelas de demonstração administradas pelo seeder. |

As associações usadas pela aplicação são lógicas. O DDL de instalação não declara chaves estrangeiras entre essas tabelas.

![Modelo operacional de dados](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/diagrams/pt-br/02-operational-model.png)

O fluxo atual cria receitas na revisão 1 e não oferece editor de revisões. O campo `SeedTask.RecipeRevision` armazena o identificador da receita. O executor resolve esse identificador para a versão mais recente no momento da execução.

## 5. Inspeção de registros: paginação por chave e prévias limitadas

`explorer.page` usa paginação por chave. A consulta de uma página seguinte compara a chave com o último valor retornado:

```sql
SELECT TOP 26
    ID,
    CASE WHEN Embedding IS NULL THEN 0 ELSE 1 END
FROM VectorFixture.Raw
WHERE ID > ?
ORDER BY ID
```

A consulta retorna 25 registros e uma linha adicional para indicar a existência de outra página. A requisição inicial não carrega vetores completos. A tela seleciona o texto de origem somente quando o vínculo está comprovado e limita esse texto a 1.200 caracteres.

A ação **Preview vector** faz uma requisição separada. O backend usa `%EXTERNAL`, calcula a norma euclidiana como `sqrt(max(0, VECTOR_DOT_PRODUCT(v,v)))` e retorna no máximo 32 valores. Ele materializa o vetor do registro selecionado até a dimensão máxima aceita de 16.384; o limite de 32 se aplica à resposta.

Os contadores do inventário descrevem a página atual. A tela não executa `COUNT(*)` nas tabelas de dados.

![Registros de um embedding gerenciado](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/02-records.png)

## 6. Busca por similaridade e inspeção do plano SQL

`search.build` combina identificadores obtidos do catálogo com valores parametrizados. Uma busca numérica de três dimensões tem este formato:

```sql
SELECT TOP 3
    "ID",
    VECTOR_COSINE("Embedding",TO_VECTOR(?, DOUBLE)) AS Score
FROM "VectorFixture"."Raw"
ORDER BY Score DESC
```

O parâmetro pode ser `'[1,0,0]'`. Antes da execução, o backend valida dimensão, tipo numérico e valores finitos. Booleanos, `NaN` e infinito são rejeitados. `VECTOR_DOT_PRODUCT` também é suportado, com scores em ordem decrescente.

Em uma coluna gerenciada, o vetor da consulta vem de `EMBEDDING`:

```sql
SELECT TOP 3
    "ID",
    VECTOR_COSINE("Embedding",EMBEDDING(?, ?)) AS Score
FROM "VectorFixture"."Managed"
ORDER BY Score DESC
```

Os parâmetros são o texto, como `vector search`, e a configuração identificada pelo catálogo. `EMBEDDING` continua exigindo os privilégios SQL do IRIS para a operação, incluindo `%USE_EMBEDDING`.

Antes de executar a busca, `search.execute` obtém `EXPLAIN`. O diagnóstico procura uma linha `Read index map` correspondente a um índice HNSW encontrado no catálogo e retorna `HNSW used`, `Full scan` ou `Undetermined`. `EXPLAIN` descreve o plano de acesso; ele não mede recall nem fornece um perfil completo de execução.

O Top K é limitado a 100. Locks do IRIS protegem dois slots de concorrência entre processos WSGI. O tempo exibido inclui a obtenção do plano e a execução da consulta. O modo `indexed` verifica a existência de um índice compatível e não força o otimizador com hint SQL.

![Busca por similaridade com resultado apoiado por HNSW](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/03-search.png)

## 7. HNSW: propostas validadas e execução assíncrona

`indexes.preflight` verifica dimensão fixa, elementos `DOUBLE` ou `DECIMAL`, storage `%Storage.Persistent`, IDs compatíveis com bitmap, privilégio `ALTER` e ausência de outro índice HNSW na coluna. O perfil habilitado usa `M=24` e `efConstruction=100`.

Para uma tabela elegível sem índice HNSW, o DDL gerado tem este formato:

```sql
CREATE INDEX "DocumentHNSW"
ON TABLE "VectorFixture"."Unindexed" ("Embedding")
AS HNSW(Distance='Cosine', M=24, efConstruction=100)
```

`DotProduct` exige que o operador declare os vetores normalizados. O preflight registra essa afirmação; ele não percorre a tabela para verificar a normalização.

![Fluxo de criação de HNSW](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/diagrams/pt-br/03-hnsw-workflow.png)

O `UPDATE` condicional precisa afetar exatamente uma linha, permitindo o consumo único de cada proposta entre processos. Depois do DDL, o worker procura a definição criada e registra um plano de verificação. Um erro de observação após a emissão do DDL pode produzir `UNKNOWN`. Consulte o catálogo para determinar o resultado antes de tentar outra operação.

![Inventário de índices HNSW e formulário de criação protegida](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/05-indexes.png)

## 8. Receitas: preencher uma nova coluna vetorial

Uma receita define namespace, tabela de destino, nova coluna, coluna de relacionamento, origem do texto, dimensão, gerador e política de repetição. O SQL de origem segue este formato restrito:

```sql
SELECT ID, Description FROM data.Document
```

A primeira coluna identifica a linha de destino. A segunda fornece o texto. O parser aceita duas colunas simples e uma tabela qualificada. Aliases, joins, expressões, filtros e ponto e vírgula final são rejeitados. Origem e destino podem ser tabelas diferentes no namespace selecionado quando suas chaves de relacionamento correspondem.

O preflight rejeita chaves nulas ou duplicadas na origem e no destino, verifica se a coluna de destino é nova e testa o gerador quando a primeira linha da origem contém texto não nulo. Ele retorna o comando `ALTER TABLE` e o alvo exato para confirmação. A publicação salva o estado da receita e a definição da tarefa. **Run now** cria e preenche a coluna de destino.

`catalog.source_tables` fornece as tabelas do seletor. Ele sugere uma coluna de relacionamento chamada `ID` ou com nome terminado em `ID`. O preflight verifica unicidade e valores nulos; a sugestão, isoladamente, não comprova essas propriedades.

![Tarefa de nova coluna vetorial configurada para data.Document](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/06-vector-tasks.png)

![Execução da receita e da tarefa](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/diagrams/pt-br/04-recipe-sequence.png)

### Geração pelo mecanismo de embeddings do IRIS

No modo `MODEL`, o executor lê a configuração e usa `EMBEDDING` no `UPDATE`. Uma receita de 16 dimensões produz DDL neste formato:

```sql
ALTER TABLE "data"."Document"
ADD "DescriptionVector" VECTOR(DOUBLE,16)
```

```sql
UPDATE "data"."Document"
SET "DescriptionVector" = EMBEDDING(?,?)
WHERE "ID" = ?
```

O vetor é gravado na linha de destino. Uma chave de origem sem destino correspondente incrementa o contador de destino ausente e mantém a tabela de dados inalterada.

`%Embedding.Config` conecta o nome da configuração SQL à classe do provedor. A fixture registra `%Embedding.SentenceTransformers` com o caminho de um modelo local. `EMBEDDING` chama esse provedor, que carrega o pipeline SentenceTransformers e seu modelo PyTorch no ambiente IRIS.

A montagem do modelo em `tools/fixtures.py` usa estes componentes após salvar em `base` um tokenizer e um BERT inicializado aleatoriamente:

```python
SentenceTransformer(modules=[
    models.Transformer(str(base), max_seq_length=64),
    models.Pooling(16),
    models.Normalize()
]).save(str(model_path))
```

Transformers fornece o BERT e o tokenizer; SentenceTransformers aplica codificação dos tokens, pooling e normalização para produzir um vetor de 16 valores. A fixture usa um vocabulário de oito tokens e pesos aleatórios para testes de integração offline. A avaliação semântica exige um modelo treinado para os documentos e o idioma pretendidos.

**Embedding configs** lê nomes de configurações, classes de provedores, dimensões e parâmetros públicos permitidos por `/api/instances/local/embedding-configs`. A tela permite inspecionar as configurações; o registro dos provedores ocorre fora dessa interface.

![Configurações de embedding disponíveis](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/08-configurations.png)

### Geração por função Python

O modo `PYTHON` aceita `generate(row, context)`. Este exemplo de três dimensões fornece características numéricas para testar o fluxo:

```python
def generate(row, context):
    text = row["text"] or ""
    return [float(len(text)), float(row["key"]), 1.0]
```

`row` contém `key` e `text`; `context` contém `dimensions`. A função deve retornar uma lista ou tupla com exatamente essa quantidade de valores finitos.

`generators.validate` usa AST e compilação para validar sintaxe e assinatura. Imports, `global` e `nonlocal` são rejeitados. A validação não executa a função. O teste de amostra executa uma linha sem salvar o vetor. A execução da tarefa converte o resultado com `TO_VECTOR(?,DOUBLE)`.

O runtime expõe um conjunto reduzido de built-ins. A funcionalidade executa código Python de administradores confiáveis dentro do IRIS; essas restrições não formam um sandbox de segurança. O cancelamento SQL não impõe limite de CPU ao código Python arbitrário.

![Gerador Python com validação de sintaxe e amostra](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/07-python-editor.png)

## 9. Reexecução, assinaturas e transações por linha

`seed_runner.execute` lê a origem em lotes de 100 linhas ordenados pela chave. Cada execução reinicia a leitura. Para cada linha, ele verifica o vetor de destino e as assinaturas de `SeedRow` antes de decidir se deve gerar.

| Política | Comportamento |
| --- | --- |
| `ALL` | Regenera linhas com destino correspondente e texto de origem não nulo. |
| `MISSING` | Gera linhas cujo vetor de destino está ausente. |
| `CHANGED` | Gera linhas sem vetor ou com assinaturas de origem/gerador alteradas. |

```python
def should_generate(policy, present, previous, source_hash, generator_hash):
    if not present or policy == 'ALL':
        return True
    if policy == 'MISSING':
        return False
    return previous != [source_hash, generator_hash]
```

`SourceHash` é calculado sobre o texto. `GeneratorHash` inclui modo de geração, dimensões, configuração ou digest do código. No modo modelo, inclui também os campos lidos de `%Embedding.Config`. Uma troca silenciosa dos pesos externos com a mesma configuração registrada preserva a mesma assinatura.

Um lock por namespace, tabela e coluna serializa os executores do portal para um destino. `SeedBegin`, `SeedCommit` e `SeedRollback`, implementados em ObjectScript, delimitam a transação que contém a atualização do vetor e de suas assinaturas. A geração Python é validada antes da abertura da transação; no modo modelo, `EMBEDDING` é avaliado no `UPDATE`.

Linhas confirmadas continuam disponíveis quando uma linha posterior falha. Uma nova execução com `CHANGED` pode ignorar essas linhas pelas assinaturas. A última chave e o heartbeat registram progresso; o executor não retoma a leitura a partir de um cursor persistido.

Os contadores distinguem vetores recém-preenchidos (`created`), vetores substituídos (`updated`), linhas ignoradas (`skipped`), falhas (`failed`) e chaves de origem sem destino (`missing`). Destinos ausentes também incrementam `skipped`, portanto `missing` é um subconjunto dessa contagem. A política reduz gerações e gravações para linhas inalteradas, enquanto cada execução continua lendo a origem e verificando cada relacionamento.

O executor Python chama métodos ObjectScript por `iris.cls('VectorAdmin.Runtime')`. Os métodos de transação em `iris/Runtime.cls` são:

```objectscript
ClassMethod SeedBegin()
{
    tstart
}

ClassMethod SeedCommit()
{
    tcommit
}

ClassMethod SeedRollback()
{
    if $tlevel { trollback 1 }
}
```

O executor inicia a transação, atualiza o destino por `iris.sql.exec`, grava `SeedRow` no namespace administrativo e confirma. Uma falha dentro dessa transação reverte as duas gravações. A criação da coluna ocorre antes desse laço e pode permanecer após uma execução com falha. O lock de destino coordena os executores do portal; outros processos da aplicação ainda podem modificar a origem ou o destino.

## 10. Task Manager, SysAdmin e observabilidade

`VectorAdmin.SeedTask` conecta o agendador do IRIS ao executor Python:

```objectscript
Class VectorAdmin.SeedTask Extends %SYS.Task.Definition
{
Parameter TaskName = "Vector recipe seed";
Property RecipeRevision As %String(MAXLEN = 32);

Method OnTask() As %Status [ Language = python ]
{
    import sys
    sys.path.insert(0, '/usr/irissys/csp/vector-admin')
    from vector_admin.recipes import run_recipe
    run_recipe(self.RecipeRevision)
    return 1
}
}
```

A classe usa `Language = python`. O portal cria tarefas como `On Demand` e define `RunAsUser` com o operador.

`recipes.create_schedule` envia a definição da tarefa para `POST /v2/task` e registra o ID retornado em `SeedSchedule`. Quando o usuário seleciona **Run now**, `tasks.run_now` verifica a classe da tarefa e envia esta requisição:

```python
client.post('/v2/task/run', {'RunNow': True, 'Datetime': ''}, id=task_id)
```

A API retorna `QUEUED` após o envio. O Task Manager chama `OnTask` em seu processo de tarefa, onde `run_recipe` carrega a receita publicada e chama `seed_runner.execute`. Fechar o navegador mantém essa execução sob controle do Task Manager. A interface atual oferece execução sob demanda e consulta de histórico; os controles de agendamento recorrente, suspensão, cancelamento e exclusão estão fora do escopo implementado.

O cliente SysAdmin usa uma allowlist derivada do contrato versionado em `vendor/`. `vendor/sysadmin-revision.txt` registra a revisão, e `tools/contract_map.py` gera o mapa de métodos, parâmetros e respostas. O cliente restringe o endereço administrativo ao loopback, bloqueia redirecionamentos e envia credenciais apenas ao endpoint local configurado.

O monitor combina `/v2/tasks`, `/v2/task`, `/v2/task/info`, `/v2/task/manager` e `/v2/task/history` com `SeedRun` e `SeedMetrics`. A aplicação valida a definição da tarefa contra `VectorAdmin.SeedTask` e combina o estado do agendador com os resultados por linha. Uma tarefa pode terminar como `SUCCEEDED_WITH_ERRORS` quando algumas linhas falham.

A listagem inicial envia `filter='VectorAdmin'` para `/v2/tasks` e depois verifica a classe de cada tarefa retornada. O exemplo usa um nome iniciado por `VectorAdmin` para corresponder a esse filtro de listagem.

A interface faz polling a cada 5 a 30 segundos conforme os dados mudam. O polling para quando a página fica oculta ou o usuário sai da tela de tarefas.

![Status do Task Manager e lista de tarefas vetoriais](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/10-task-monitor.png)

## 11. Do namespace ao diretório: localização do storage vetorial

`placement.inspect` conecta os metadados SQL ao storage do IRIS. Ele lê `DataLocation`, `IdLocation`, `IndexLocation` e `StreamLocation` de `%Dictionary.CompiledStorage`, depois combina esses globals com defaults do namespace, mappings e inventário de bancos retornado pela SysAdmin.

![Resolução da localização do storage](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/diagrams/pt-br/05-storage-placement.png)

A fixture `VectorFixture.Mapped` usa globals separados para dados e índices: `^VectorFixtureMappedD` e `^VectorFixtureMappedI`. Os scripts de fixture configuram mappings para exercitar essa resolução.

O resolvedor informa apenas relações estabelecidas pelos metadados disponíveis. Storage customizado, expressões de subscrito, mappings sobrepostos e precedência desconhecida produzem dados parciais ou `Unresolved`. A tela exibe a evidência e a razão do resultado.

![Globals de storage, bancos e diretórios](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/04-placement.png)

## 12. Autorização e controles de execução

A aplicação web do IRIS usa autenticação Basic e exige `VectorAdmin_Read`. O backend verifica os recursos do operador e armazena a identidade da requisição em um `ContextVar`. Essas verificações complementam os privilégios nativos de SQL, banco e API administrativa.

| Papel | Recursos do portal |
| --- | --- |
| `VectorAdminReader` | `VectorAdmin_Read`. |
| `VectorAdminMaintainer` | `VectorAdmin_Read` e `VectorAdmin_Maintain`. |
| `VectorAdminAdministrator` | `VectorAdmin_Read` e `VectorAdmin_Admin`. |

`Administrator` não inclui `Maintain`. O instalador também atribui `%DB_USER:R` e `%Admin_Manage:U` ao papel de leitura da demonstração. As permissões de tabela permanecem separadas.

As requisições POST exigem token CSRF e validam o cabeçalho `Origin` quando presente. Tokens HMAC-SHA256 incluem finalidade, operador e expiração. Valores SQL usam parâmetros, identificadores são delimitados e corpos JSON têm limite de 128 KiB.

`VectorAdmin.Runtime` usa eventos e um processo observador para solicitar o cancelamento de consultas SQL após o orçamento configurado. O padrão é 10 segundos, com janelas maiores para operações específicas. O IRIS coordena locks entre workers Python.

A auditoria armazena metadados operacionais selecionados sem argumentos SQL, texto de documentos ou valores vetoriais. A tela de configurações de embedding expõe apenas `modelName`, `maxTokens` e `checkTokenCount` do JSON de configuração. As flags de capacidade mantêm indisponíveis a edição genérica de registros, a edição de configurações e a remoção ou reconstrução de índices; tarefas de geração autorizadas gravam sua coluna vetorial pelo fluxo específico.

![Versão instalada do IRIS, recursos habilitados e limites](https://raw.githubusercontent.com/Davi-Massaru/iris-vector-management/refs/heads/master/docs/screenshots/09-capabilities.png)

## 13. Exemplo prático: manter os vetores dos documentos conforme a origem muda

Uma aplicação armazena descrições em `data.Document`. A tarefa adiciona um vetor a cada documento e o atualiza quando a descrição muda. `CHANGED` permite reutilizar uma tarefa e preservar os vetores das descrições inalteradas. Este exemplo demonstra o fluxo de geração e persistência com a fixture offline do repositório.

### Preparar a demonstração

Use Git, Docker com Compose v2 e suporte a containers Linux. Clone o projeto e siga a [instalação do README](README.md#install-and-try-it) para criar `.env` e o arquivo de senha `.local/iris-password.txt`, com uma linha em UTF-8. Mantenha `WITH_FIXTURES=1` e execute:

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f iris
```

Após concluir a inicialização, abra [o portal local](http://localhost:52773/vector-admin/), entre com a conta local `_SYSTEM` e a senha configurada e selecione `USER`. O build fornece 20 documentos do Faker e `vector-fixture-tiny`. A tabela de documentos aparece no seletor de tarefas antes de ter uma coluna vetorial; ela aparece no inventário de vetores após a primeira execução criar essa coluna.

### Criar e executar a receita

Abra **Vector tasks** e preencha:

| Campo | Valor |
| --- | --- |
| Nome da receita | `VectorAdmin Document descriptions` |
| Tabela de destino | `data.Document` |
| Nova coluna vetorial | `DescriptionVector` |
| Coluna de relacionamento | `ID` |
| Dimensões | `16` |
| Geração | `Embedding model` |
| Configuração de embedding | `vector-fixture-tiny` |
| Política de reexecução | `Novos ou alterados` (`CHANGED`) |
| SQL de origem | `SELECT ID, Description FROM data.Document` |

Marque o teste de amostra, selecione **Validate and preview** e revise o DDL. Confirme `USER/data.Document/DescriptionVector`, selecione **Publish and create task** e anote o ID da tarefa. Use **Run now** nessa tarefa e abra o painel de detalhes para consultar os contadores da execução.

Após a conclusão, atualize o inventário e inspecione `data.Document.DescriptionVector`. **Records** mostra a presença do vetor, e **Preview vector** retorna seus valores. A coluna é um `VECTOR` comum, portanto origem e modelo podem permanecer como `Unknown` no catálogo. A receita publicada contém sua definição operacional.

Em um editor SQL do IRIS conectado ao namespace `USER`, confira os valores persistidos:

```sql
SELECT TOP 5
    ID,
    Description,
    CASE WHEN DescriptionVector IS NULL THEN 0 ELSE 1 END AS HasVector,
    %EXTERNAL(DescriptionVector) AS VectorValues
FROM data.Document
ORDER BY ID
```

Execute a mesma tarefa novamente. Com descrições e configuração do gerador inalteradas, `CHANGED` ignora as 20 linhas. Continue usando essa tarefa para a coluna; uma receita de nova coluna com o mesmo nome de destino retorna `TARGET_EXISTS`.

### Alterar um documento e adicionar dois

Execute os comandos a seguir uma vez no editor SQL da base de demonstração. Eles alteram a descrição de `ID=1` e adicionam dois documentos. Confirme na consulta anterior que `ID=1` existe ou substitua por um ID existente. O portal não oferece um formulário genérico para editar documentos.

```sql
UPDATE data.Document
SET Description = 'Documento atualizado sobre busca vetorial no IRIS.',
    UpdatedAt = CURRENT_TIMESTAMP
WHERE ID = 1;

INSERT INTO data.Document (Description, CreatedAt, UpdatedAt)
VALUES ('Novo documento sobre armazenamento de dados.',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO data.Document (Description, CreatedAt, UpdatedAt)
VALUES ('Novo documento sobre busca por similaridade.',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
```

Origem e destino são a mesma tabela neste exemplo, portanto os novos documentos já possuem linhas correspondentes no destino. Execute **Run now** novamente. O executor preenche seus vetores e substitui o vetor do documento alterado. Com uma base inicial de 20 linhas, descrições não nulas e gerações bem-sucedidas, os resultados esperados são:

| Execução | Estado da origem | Lidos | Criados | Atualizados | Ignorados |
| --- | --- | --- | --- | --- | --- |
| 1 | 20 documentos originais | 20 | 20 | 0 | 0 |
| 2 | Sem alterações | 20 | 0 | 0 | 20 |
| 3 | Uma descrição alterada e dois documentos novos | 22 | 2 | 1 | 19 |
| 4 | Sem alterações após a execução 3 | 22 | 0 | 0 | 22 |

`failed` e `missing` devem permanecer em zero. Essas contagens decorrem da lógica do executor e representam expectativas para o exemplo. `tools/acceptance_repeatable_http.py` verifica o mesmo padrão de alterações com o gerador Python de três dimensões. A política evita geração e gravação de vetores para linhas inalteradas, mantendo a leitura completa da origem.

### Inspecionar similaridade e uso de índices

Para um exemplo numérico determinístico, inspecione `VectorFixture.Raw.Embedding`, abra **Similarity search**, escolha entrada vetorial, `Cosine` e Top K `3` e busque por `[1, 0, 0]`. A fixture contém `[1,0,0]`, `[0,1,0]`, `[0,0,1]` e `[0.7,0.7,0]`. Seus scores de cosseno em relação à consulta são aproximadamente `1`, `0`, `0` e `0,7071`. As duas linhas com score zero empatam no limite do resultado, e a consulta usa somente o score na ordenação.

Expanda **Query plan & SQL** para inspecionar o caminho de acesso escolhido pelo otimizador. Para exercitar a criação de índice, inspecione `VectorFixture.Unindexed.Embedding`, faça uma busca antes da criação e abra **Indexes**. Se a coluna ainda estiver sem HNSW, valide `DocumentHNSW` com `Cosine`, confirme o alvo exibido e aguarde o resultado da operação. Repita a busca e compare o diagnóstico do plano. Essa fixture inclui um vetor zero, excluído de um índice HNSW com Cosine.

A entrada textual está disponível em `VectorFixture.Managed.Embedding`, cujo esquema vincula origem e configuração. Use `vector search` para exercitar o provedor. A fixture com pesos aleatórios valida a integração; a qualidade semântica exige um modelo de embedding treinado. Para `DescriptionVector`, o portal atual aceita consultas numéricas porque os metadados do catálogo não possuem um vínculo textual gerenciado. Vetores usados para consultar documentos reais devem compartilhar o modelo, as dimensões e o pré-processamento dos vetores armazenados.

Se a inicialização do modelo falhar, use uma nova coluna chamada `DescriptionFeatures`, selecione **Python function**, defina três dimensões e cole o gerador da seção 8. Valide a sintaxe, teste uma amostra e publique com `CHANGED`. Esse caminho exercita criação de coluna e atualizações repetíveis com características numéricas de tamanho do texto e chave. O resultado representa essas características e não contém uma codificação semântica da descrição.

## 14. Instalação e verificações do repositório

O `Dockerfile` copia a aplicação, instala dependências, inicia temporariamente o IRIS para compilar classes, configura a aplicação web, cria tabelas operacionais e carrega as fixtures habilitadas. O Compose publica a porta 52773 em `127.0.0.1` e monta a senha local de `_SYSTEM` como secret. O [README](README.md) documenta a preparação de `.env` e `.local/iris-password.txt`.

Os comandos de build e inicialização estão na seção 13. A configuração Compose fornecida não possui volume persistente para os bancos. Recriar ou remover o container pode descartar receitas, tarefas, índices e dados criados em execução. `docker compose stop` e `docker compose start` preservam o mesmo container.

As verificações do repositório incluem testes unitários e scripts que exigem uma instância IRIS. `tests/test_core.py` cobre validação vetorial, SQL parametrizado, tokens, configurações públicas, mappings e diagnóstico HNSW. `tests/test_repeatable.py` cobre políticas de repetição e validação de sintaxe Python.

```sh
docker compose exec -T -w /usr/irissys/csp/vector-admin iris python3 -m unittest discover -s tests -v
```

`tools/smoke.py` e `tools/integration.py` verificam a integração com o runtime. `tools/acceptance_vector_creation.py` exercita a criação de colunas. `tools/acceptance_repeatable_http.py` percorre a API HTTP, cria tarefas reais, altera documentos de demonstração e verifica `CHANGED`, `MISSING` e `ALL`. Seu gerador Python permite testar agendamento e persistência independentemente da inicialização do modelo.

`tools/acceptance.py` exercita busca gerenciada, criação protegida de HNSW e cancelamento SQL. Sua execução também cria a tabela `VectorFixture.Large` com 500 mil linhas quando ela está ausente. O build normal omite essa tabela. O script grava as verificações observadas em `docs/acceptance-evidence.json`; interprete os tempos no contexto da máquina e dos dados usados naquela execução. Esses scripts alteram dados de demonstração e devem rodar em uma instância descartável.

Para alterações locais, `docker compose config --quiet` verifica a configuração do Compose, e `node --check vector_admin/static/app.js` verifica a sintaxe JavaScript quando o Node.js está disponível. Após editar código, reconstrua a imagem para incluí-lo: o Compose fornecido copia os arquivos durante o build e não monta o código por bind mount. Preserve os dados de execução antes de recriar o container.

## Código que fundamenta o artigo

- [Entrada WSGI e rotas](vector_admin/app.py), [instalação no IRIS](iris/install.script) e [configuração do container](Dockerfile).
- [Catálogo compilado](vector_admin/catalog.py), [inspeção de registros](vector_admin/explorer.py) e [localização física](vector_admin/placement.py).
- [Busca e planos](vector_admin/search.py) e [criação de índices](vector_admin/indexes.py).
- [Receitas](vector_admin/recipes.py), [validação Python](vector_admin/generators.py) e [executor repetível](vector_admin/seed_runner.py).
- [Classe de tarefa](iris/SeedTask.cls), [coordenação ObjectScript](iris/Runtime.cls) e [cliente SysAdmin](vector_admin/sysadmin_client.py).
- [Esquema operacional](tools/install.py), [fixtures vetoriais](tools/fixtures.py) e [testes de repetição via HTTP](tools/acceptance_repeatable_http.py).
- [Interface do navegador](vector_admin/static/app.js), [acesso ao namespace e SQL](vector_admin/sql.py), [configurações de embedding](vector_admin/configs.py) e [mapa da SysAdmin API](docs/sysadmin-api-map.md).
