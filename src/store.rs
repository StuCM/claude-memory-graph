use std::path::PathBuf;

use oxigraph::io::{RdfFormat, RdfParser, RdfSerializer};
use oxigraph::model::{GraphName, NamedNode, Quad};
use oxigraph::sparql::{QueryResults, SparqlEvaluator};
use oxigraph::store::Store;
use tracing::info;

use crate::namespaces::{self, GRAPH_SCHEMA, SPARQL_PREFIXES};

#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error("Oxigraph store error: {0}")]
    Store(#[from] oxigraph::store::StorageError),
    #[error("SPARQL evaluation error: {0}")]
    Sparql(#[from] oxigraph::sparql::QueryEvaluationError),
    #[error("SPARQL update error: {0}")]
    Update(#[from] oxigraph::sparql::UpdateEvaluationError),
    #[error("RDF parse error: {0}")]
    Parse(#[from] oxigraph::io::RdfParseError),
    #[error("RDF loader error: {0}")]
    Loader(#[from] oxigraph::store::LoaderError),
    #[error("SPARQL syntax error: {0}")]
    SparqlSyntax(#[from] oxigraph::sparql::SparqlSyntaxError),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("{0}")]
    Other(String),
}

pub struct MemoryStore {
    store: Store,
    data_path: Option<PathBuf>,
}

impl MemoryStore {
    /// Create an in-memory store, loading persisted data from an NQuads file if it exists.
    pub fn open_or_create(data_dir: PathBuf) -> Result<Self, StoreError> {
        std::fs::create_dir_all(&data_dir)?;
        let data_path = data_dir.join("graph.nq");
        let store = Store::new()?;

        // Load persisted data if the file exists
        if data_path.exists() {
            info!("Loading persisted data from {}", data_path.display());
            let data = std::fs::read_to_string(&data_path)?;
            let parser = RdfParser::from_format(RdfFormat::NQuads);
            store.load_from_reader(parser, data.as_bytes())?;
            info!("Persisted data loaded");
        }

        let ms = Self {
            store,
            data_path: Some(data_path),
        };
        ms.ensure_base_ontology()?;
        Ok(ms)
    }

    /// Create a purely in-memory store (for tests).
    #[allow(dead_code)]
    pub fn new_in_memory() -> Result<Self, StoreError> {
        let store = Store::new()?;
        let ms = Self {
            store,
            data_path: None,
        };
        ms.ensure_base_ontology()?;
        Ok(ms)
    }

    /// Dump all quads to the NQuads file for persistence.
    pub fn save(&self) -> Result<(), StoreError> {
        let Some(path) = &self.data_path else {
            return Ok(());
        };
        info!("Saving graph to {}", path.display());
        let file = std::fs::File::create(path)?;
        let serializer = RdfSerializer::from_format(RdfFormat::NQuads);
        let mut writer = serializer.for_writer(file);
        for quad in self.store.iter() {
            writer
                .serialize_quad(&quad?)
                .map_err(|e| StoreError::Other(e.to_string()))?;
        }
        writer
            .finish()
            .map_err(|e: std::io::Error| StoreError::Other(e.to_string()))?;
        info!("Graph saved");
        Ok(())
    }

    /// Load the base ontology into mem:schema if it's not already there.
    fn ensure_base_ontology(&self) -> Result<(), StoreError> {
        let schema_graph = namespaces::graph_node(GRAPH_SCHEMA);

        let has_schema = self
            .store
            .quads_for_pattern(None, None, None, Some(schema_graph.as_ref().into()))
            .next()
            .is_some();

        if !has_schema {
            info!("Loading base ontology into schema graph");
            let ttl = include_str!("../ontology/base.ttl");
            let parser = RdfParser::from_format(RdfFormat::Turtle)
                .with_default_graph(GraphName::NamedNode(schema_graph));
            self.store.load_from_reader(parser, ttl.as_bytes())?;
            info!("Base ontology loaded");
        }

        Ok(())
    }

    /// Insert a quad into the store.
    pub fn insert(&self, quad: &Quad) -> Result<(), StoreError> {
        self.store.insert(quad)?;
        Ok(())
    }

    /// Insert multiple quads.
    pub fn insert_many(&self, quads: &[Quad]) -> Result<(), StoreError> {
        for quad in quads {
            self.store.insert(quad)?;
        }
        Ok(())
    }

    /// Remove a quad from the store.
    pub fn remove(&self, quad: &Quad) -> Result<(), StoreError> {
        self.store.remove(quad)?;
        Ok(())
    }

    /// Run a SPARQL SELECT/CONSTRUCT/ASK query with standard prefixes prepended.
    pub fn query(&self, sparql: &str) -> Result<QueryResults<'_>, StoreError> {
        let full_query = format!("{SPARQL_PREFIXES}\n{sparql}");
        let results = SparqlEvaluator::new()
            .parse_query(&full_query)?
            .on_store(&self.store)
            .execute()?;
        Ok(results)
    }

    /// Run a SPARQL UPDATE with standard prefixes prepended.
    pub fn update(&self, sparql: &str) -> Result<(), StoreError> {
        let full_update = format!("{SPARQL_PREFIXES}\n{sparql}");
        SparqlEvaluator::new()
            .parse_update(&full_update)?
            .on_store(&self.store)
            .execute()?;
        Ok(())
    }

    /// Check if a node IRI exists in the knowledge graph.
    pub fn node_exists(&self, iri: &NamedNode) -> Result<bool, StoreError> {
        let knowledge_graph = namespaces::graph_node(namespaces::GRAPH_KNOWLEDGE);
        Ok(self
            .store
            .quads_for_pattern(
                Some(iri.as_ref().into()),
                None,
                None,
                Some(knowledge_graph.as_ref().into()),
            )
            .next()
            .is_some())
    }

    /// Find a node by type and name/label in the knowledge graph.
    pub fn find_node_by_name(
        &self,
        node_type: &str,
        name: &str,
    ) -> Result<Option<NamedNode>, StoreError> {
        let sparql = format!(
            r#"SELECT ?node WHERE {{
                GRAPH <{graph}> {{
                    ?node rdf:type mem:{node_type} .
                    ?node mem:name "{name}" .
                }}
            }} LIMIT 1"#,
            graph = namespaces::GRAPH_KNOWLEDGE,
        );

        match self.query(&sparql)? {
            QueryResults::Solutions(mut solutions) => {
                if let Some(Ok(solution)) = solutions.next() {
                    if let Some(oxigraph::model::Term::NamedNode(nn)) = solution.get("node") {
                        return Ok(Some(nn.clone()));
                    }
                }
                Ok(None)
            }
            _ => Ok(None),
        }
    }

    /// Get the raw oxigraph store (for advanced operations).
    #[allow(dead_code)]
    pub fn inner(&self) -> &Store {
        &self.store
    }
}
