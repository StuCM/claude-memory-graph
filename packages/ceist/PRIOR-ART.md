# Prior art and credits

Ceist builds on published research. This page records what we took from each source and where it is used. When a module uses a borrowed method, its docstring names the source in one line and points here.

Entries marked *(not checked against the paper)* are cited from memory and need checking before anything is published.

## Methods Ceist uses or follows

| Source | What we take from it | Where |
| --- | --- | --- |
| Popescu, A.-M., Etzioni, O., Kautz, H. (2003). *Towards a theory of natural language interfaces to databases.* IUI '03. *(not checked against the paper)* | Answer only "semantically tractable" questions: those whose words map to schema elements with exactly one consistent reading; refuse the rest. The matching formulation, and the "tractable %" measure. | never-guess throughout; schema assembly (task 049) |
| Wang, Y., Berant, J., Liang, P. (2015). *Building a Semantic Parser Overnight.* ACL 2015. [ACL Anthology P15-1129](https://aclanthology.org/P15-1129/) | Canonical utterances: generate the questions a grammar can answer, in plain readable form, then collect natural paraphrases of them. | Narration of plans; planned: enumerating answerable questions from the schema, and paraphrasing them at build time |
| Herzig, J., Berant, J. (2019). *Don't paraphrase, detect! Rapid and Effective Data Collection for Semantic Parsing.* EMNLP-IJCNLP 2019. [arXiv:1908.09940](https://arxiv.org/abs/1908.09940) | Picking the right reading from candidates is cheaper and more accurate than writing paraphrases. | Planned: a visitor's "did you mean" choice becomes confirmed vocabulary (capture loop) |
| Wu, S., Chen, B., Xin, C., Han, X., Sun, L., Zhang, W., Chen, J., Yang, F., Cai, X. (2021). *From Paraphrasing to Semantic Parsing: Unsupervised Semantic Parsing via Synchronous Semantic Decoding.* ACL-IJCNLP 2021, 5110–5121. [doi:10.18653/v1/2021.acl-long.397](https://aclanthology.org/2021.acl-long.397) | Parsing as constrained paraphrasing into a canonical form, with grammar-constrained decoding. | Background for the rewriter experiment; constraining any build-time LLM paraphrase to Ceist's grammar |
| Shin, R., et al. (2021). *Constrained Language Models Yield Few-Shot Semantic Parsers.* EMNLP 2021. *(not checked against the paper)* | A language model rewrites a question into canonical English, constrained by a grammar. | Background for the rewriter experiment (an LLM at question time, which we rejected) |
| Mountantonakis, M., Tzitzikas, Y. (2025). *Generating SPARQL Queries over CIDOC-CRM using a Two-Stage Ontology Path Patterns Method in LLM Prompts.* ACM Journal on Computing and Cultural Heritage. [doi:10.1145/3708326](https://dl.acm.org/doi/full/10.1145/3708326) | Questions over CIDOC-CRM are answered by following ontology path patterns. Their 100-question benchmark over two CRM graphs. | The ontology layer's path phrasings (built independently, the same idea); planned: their benchmark as an outside test |
| Li, F., Jagadish, H. V. (2014). *Constructing an Interactive Natural Language Interface for Relational Databases* (NaLIR). PVLDB 8(1). *(not checked against the paper)* | Ask the user when several readings fit. | "Did you mean" on ambiguity (task 049) |
| Saha, D., et al. (2016). *ATHENA: An Ontology-Driven System for Natural Language Querying over Relational Data Stores.* PVLDB 9(12). *(not checked against the paper)* | Ontology-driven interpretation, with readings ranked by how compact they are. | Planned: ordering "did you mean" options (never to pick one) |
| Chapman, W. W., et al. (2001). *A simple algorithm for identifying negated findings and diseases in discharge summaries* (NegEx). Journal of Biomedical Informatics 34(5). *(not checked against the paper)* | Negation scope by a window of words after the negator. | `ground` negation scoping |

## Related work (context, nothing taken)
- QUEST, a natural language interface to relational databases with offline-generated lexicalised rules and an online rule-based parser. LREC 2018. [L18-1469](https://aclanthology.org/L18-1469.pdf)
- Surveys of LLM text-to-SQL ([arXiv:2406.08426](https://arxiv.org/pdf/2406.08426)) and of natural language interfaces to spatial and temporal databases ([arXiv:2603.23375](https://arxiv.org/pdf/2603.23375)).

## Data and models
- **CIDOC CRM and CRMsci:** CIDOC CRM SIG / FORTH-ICS. See `vocabularies/ontology/cidoc-crm/source/README` for versions, provenance and licence.
- **bge-small-en-v1.5:** BAAI.
