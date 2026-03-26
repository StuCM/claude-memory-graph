use std::collections::HashMap;
use std::path::PathBuf;

use oxigraph::io::{RdfFormat, RdfParser, RdfSerializer};
use oxigraph::model::{GraphName, Literal, NamedNode, Quad, Term};
use oxigraph::sparql::{QueryResults, SparqlEvaluator};
use oxigraph::store::Store;
use tracing::info;

use crate::namespaces::{self, GRAPH_CONCEPTS, GRAPH_LINKS, GRAPH_SCHEMA, MEM, SPARQL_PREFIXES};
use crate::ontology;
use crate::util;

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
    pub fn open_or_create(data_dir: PathBuf) -> Result<Self, StoreError> {
        std::fs::create_dir_all(&data_dir)?;
        let data_path = data_dir.join("graph.nq");
        let store = Store::new()?;

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

    // ================================================================
    // Resource instance operations (each resource = own named graph)
    // ================================================================

    /// Create a new resource instance with its own named graph.
    /// Returns (resource_id, resource_iri).
    pub fn create_resource(
        &self,
        model: &str,
        properties: &HashMap<String, String>,
    ) -> Result<(String, NamedNode), StoreError> {
        if !ontology::is_resource_model(model) {
            return Err(StoreError::Other(format!("Unknown resource model: {model}")));
        }

        let (id, iri) = util::new_resource_iri();
        let graph = namespaces::resource_graph_iri(&id);
        let graph_name = GraphName::NamedNode(graph);
        let rdf_type = namespaces::named_node(
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "type",
        );
        let mem_type = namespaces::named_node(MEM, model);
        let now = util::now_literal();

        let mut quads = vec![
            Quad::new(iri.clone(), rdf_type, mem_type, graph_name.clone()),
            Quad::new(
                iri.clone(),
                namespaces::named_node(MEM, "createdAt"),
                now.clone(),
                graph_name.clone(),
            ),
            Quad::new(
                iri.clone(),
                namespaces::named_node(MEM, "updatedAt"),
                now,
                graph_name.clone(),
            ),
        ];

        // Add scalar properties
        let valid_props = ontology::scalar_properties(model).unwrap_or(&[]);
        for (key, value) in properties {
            if valid_props.contains(&key.as_str()) {
                quads.push(Quad::new(
                    iri.clone(),
                    namespaces::named_node(MEM, key),
                    Literal::new_simple_literal(value),
                    graph_name.clone(),
                ));
            }
        }

        for quad in &quads {
            self.store.insert(quad)?;
        }

        Ok((id, iri))
    }

    /// Update scalar properties on an existing resource.
    pub fn update_resource(
        &self,
        resource_iri: &NamedNode,
        graph_id: &str,
        properties: &HashMap<String, String>,
    ) -> Result<(), StoreError> {
        let graph = namespaces::resource_graph_iri(graph_id);
        let graph_name = GraphName::NamedNode(graph.clone());

        // Find the model type
        let model = self.get_resource_type(resource_iri, &graph)?;
        let valid_props = ontology::scalar_properties(&model).unwrap_or(&[]);

        for (key, value) in properties {
            if !valid_props.contains(&key.as_str()) {
                continue;
            }
            let predicate = namespaces::named_node(MEM, key);

            // Remove old values for this property
            let old_quads: Vec<_> = self
                .store
                .quads_for_pattern(
                    Some(resource_iri.as_ref().into()),
                    Some(predicate.as_ref().into()),
                    None,
                    Some(graph.as_ref().into()),
                )
                .collect::<Result<Vec<_>, _>>()?;
            for old in &old_quads {
                self.store.remove(old)?;
            }

            // Insert new value
            self.store.insert(&Quad::new(
                resource_iri.clone(),
                predicate,
                Literal::new_simple_literal(value),
                graph_name.clone(),
            ))?;
        }

        // Update timestamp
        let updated_pred = namespaces::named_node(MEM, "updatedAt");
        let old_timestamps: Vec<_> = self
            .store
            .quads_for_pattern(
                Some(resource_iri.as_ref().into()),
                Some(updated_pred.as_ref().into()),
                None,
                Some(graph.as_ref().into()),
            )
            .collect::<Result<Vec<_>, _>>()?;
        for old in &old_timestamps {
            self.store.remove(old)?;
        }
        self.store.insert(&Quad::new(
            resource_iri.clone(),
            updated_pred,
            util::now_literal(),
            graph_name,
        ))?;

        Ok(())
    }

    /// Find a resource by model type and name.
    /// Returns (graph_id, resource_iri) if found.
    pub fn find_resource(
        &self,
        model: &str,
        name: &str,
    ) -> Result<Option<(String, NamedNode)>, StoreError> {
        let name_prop = ontology::name_property(model);
        let sparql = format!(
            r#"SELECT ?node ?g WHERE {{
                GRAPH ?g {{
                    ?node rdf:type mem:{model} .
                    ?node mem:{name_prop} "{name}" .
                }}
                FILTER(STRSTARTS(STR(?g), "{base}"))
            }} LIMIT 1"#,
            base = namespaces::GRAPH_RESOURCE_BASE,
        );

        match self.query(&sparql)? {
            QueryResults::Solutions(mut solutions) => {
                if let Some(Ok(solution)) = solutions.next() {
                    if let (Some(Term::NamedNode(iri)), Some(Term::NamedNode(graph))) =
                        (solution.get("node"), solution.get("g"))
                    {
                        let graph_str = graph.as_str();
                        let id = graph_str
                            .strip_prefix(namespaces::GRAPH_RESOURCE_BASE)
                            .unwrap_or(graph_str)
                            .to_string();
                        return Ok(Some((id, iri.clone())));
                    }
                }
                Ok(None)
            }
            _ => Ok(None),
        }
    }

    /// Get all properties of a resource as a map.
    pub fn get_resource_properties(
        &self,
        resource_iri: &NamedNode,
        graph_id: &str,
    ) -> Result<HashMap<String, String>, StoreError> {
        let graph = namespaces::resource_graph_iri(graph_id);
        let mut props = HashMap::new();

        for quad in self.store.quads_for_pattern(
            Some(resource_iri.as_ref().into()),
            None,
            None,
            Some(graph.as_ref().into()),
        ) {
            let quad = quad?;
            let pred = quad.predicate.as_str();
            if let Some(key) = pred.strip_prefix(MEM) {
                match &quad.object {
                    Term::Literal(lit) => {
                        props.insert(key.to_string(), lit.value().to_string());
                    }
                    Term::NamedNode(nn) => {
                        props.insert(key.to_string(), nn.as_str().to_string());
                    }
                    _ => {}
                }
            }
        }

        Ok(props)
    }

    /// Get the rdf:type of a resource within its graph.
    fn get_resource_type(
        &self,
        resource_iri: &NamedNode,
        graph: &NamedNode,
    ) -> Result<String, StoreError> {
        let rdf_type = namespaces::named_node(
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "type",
        );
        for quad in self.store.quads_for_pattern(
            Some(resource_iri.as_ref().into()),
            Some(rdf_type.as_ref().into()),
            None,
            Some(graph.as_ref().into()),
        ) {
            let quad = quad?;
            if let Term::NamedNode(nn) = &quad.object {
                if let Some(type_name) = nn.as_str().strip_prefix(MEM) {
                    return Ok(type_name.to_string());
                }
            }
        }
        Err(StoreError::Other("Resource type not found".into()))
    }

    // ================================================================
    // Concept operations (stored in shared concepts graph)
    // ================================================================

    /// Create or find a concept node.
    pub fn store_concept(
        &self,
        concept_type: &str,
        label: &str,
        properties: &HashMap<String, String>,
    ) -> Result<NamedNode, StoreError> {
        if !ontology::is_concept_type(concept_type) {
            return Err(StoreError::Other(format!(
                "Unknown concept type: {concept_type}"
            )));
        }

        // Check if concept already exists
        if let Some(existing) = self.find_concept(concept_type, label)? {
            return Ok(existing);
        }

        let iri = util::new_concept_iri();
        let graph = namespaces::graph_node(GRAPH_CONCEPTS);
        let graph_name = GraphName::NamedNode(graph);
        let rdf_type = namespaces::named_node(
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "type",
        );

        let mut quads = vec![
            Quad::new(
                iri.clone(),
                rdf_type,
                namespaces::named_node(MEM, concept_type),
                graph_name.clone(),
            ),
            Quad::new(
                iri.clone(),
                namespaces::named_node(MEM, "label"),
                Literal::new_simple_literal(label),
                graph_name.clone(),
            ),
            Quad::new(
                iri.clone(),
                namespaces::named_node(MEM, "createdAt"),
                util::now_literal(),
                graph_name.clone(),
            ),
        ];

        let valid_props = ontology::scalar_properties(concept_type).unwrap_or(&[]);
        for (key, value) in properties {
            if valid_props.contains(&key.as_str()) && key != "label" {
                quads.push(Quad::new(
                    iri.clone(),
                    namespaces::named_node(MEM, key),
                    Literal::new_simple_literal(value),
                    graph_name.clone(),
                ));
            }
        }

        for quad in &quads {
            self.store.insert(quad)?;
        }

        Ok(iri)
    }

    /// Find a concept by type and label.
    pub fn find_concept(
        &self,
        concept_type: &str,
        label: &str,
    ) -> Result<Option<NamedNode>, StoreError> {
        let sparql = format!(
            r#"SELECT ?node WHERE {{
                GRAPH <{graph}> {{
                    ?node rdf:type mem:{concept_type} .
                    ?node mem:label "{label}" .
                }}
            }} LIMIT 1"#,
            graph = GRAPH_CONCEPTS,
        );

        match self.query(&sparql)? {
            QueryResults::Solutions(mut solutions) => {
                if let Some(Ok(solution)) = solutions.next() {
                    if let Some(Term::NamedNode(nn)) = solution.get("node") {
                        return Ok(Some(nn.clone()));
                    }
                }
                Ok(None)
            }
            _ => Ok(None),
        }
    }

    // ================================================================
    // Cross-link operations (stored in links graph)
    // ================================================================

    /// Create a cross-link between two resources.
    pub fn create_link(
        &self,
        source_iri: &NamedNode,
        target_iri: &NamedNode,
        relation: &str,
        metadata: &HashMap<String, String>,
    ) -> Result<NamedNode, StoreError> {
        let link_iri = util::new_link_iri();
        let graph = namespaces::graph_node(GRAPH_LINKS);
        let graph_name = GraphName::NamedNode(graph);
        let rdf_type = namespaces::named_node(
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "type",
        );

        let mut quads = vec![
            Quad::new(
                link_iri.clone(),
                rdf_type,
                namespaces::named_node(MEM, "CrossLink"),
                graph_name.clone(),
            ),
            Quad::new(
                link_iri.clone(),
                namespaces::named_node(MEM, "linkSource"),
                source_iri.clone(),
                graph_name.clone(),
            ),
            Quad::new(
                link_iri.clone(),
                namespaces::named_node(MEM, "linkTarget"),
                target_iri.clone(),
                graph_name.clone(),
            ),
            Quad::new(
                link_iri.clone(),
                namespaces::named_node(MEM, "linkRelation"),
                Literal::new_simple_literal(relation),
                graph_name.clone(),
            ),
            Quad::new(
                link_iri.clone(),
                namespaces::named_node(MEM, "linkCreatedAt"),
                util::now_literal(),
                graph_name.clone(),
            ),
        ];

        // Add metadata
        for (key, value) in metadata {
            quads.push(Quad::new(
                link_iri.clone(),
                namespaces::named_node(MEM, key),
                Literal::new_simple_literal(value),
                graph_name.clone(),
            ));
        }

        for quad in &quads {
            self.store.insert(quad)?;
        }

        Ok(link_iri)
    }

    /// Remove a cross-link between two resources.
    pub fn remove_link(
        &self,
        source_iri: &NamedNode,
        target_iri: &NamedNode,
        relation: &str,
    ) -> Result<bool, StoreError> {
        let sparql = format!(
            r#"SELECT ?link WHERE {{
                GRAPH <{graph}> {{
                    ?link rdf:type mem:CrossLink .
                    ?link mem:linkSource <{source}> .
                    ?link mem:linkTarget <{target}> .
                    ?link mem:linkRelation "{relation}" .
                }}
            }} LIMIT 1"#,
            graph = GRAPH_LINKS,
            source = source_iri.as_str(),
            target = target_iri.as_str(),
        );

        let link_iri = match self.query(&sparql)? {
            QueryResults::Solutions(mut solutions) => {
                if let Some(Ok(solution)) = solutions.next() {
                    if let Some(Term::NamedNode(nn)) = solution.get("link") {
                        Some(nn.clone())
                    } else {
                        None
                    }
                } else {
                    None
                }
            }
            _ => None,
        };

        let Some(link_iri) = link_iri else {
            return Ok(false);
        };

        // Remove all quads for this link
        let graph = namespaces::graph_node(GRAPH_LINKS);
        let quads: Vec<_> = self
            .store
            .quads_for_pattern(
                Some(link_iri.as_ref().into()),
                None,
                None,
                Some(graph.as_ref().into()),
            )
            .collect::<Result<Vec<_>, _>>()?;
        for quad in &quads {
            self.store.remove(quad)?;
        }

        Ok(true)
    }

    /// Get all links from/to a resource.
    pub fn get_links_for(
        &self,
        resource_iri: &NamedNode,
    ) -> Result<Vec<LinkInfo>, StoreError> {
        let sparql = format!(
            r#"SELECT ?link ?source ?target ?relation WHERE {{
                GRAPH <{graph}> {{
                    ?link rdf:type mem:CrossLink .
                    ?link mem:linkSource ?source .
                    ?link mem:linkTarget ?target .
                    ?link mem:linkRelation ?relation .
                    FILTER(?source = <{iri}> || ?target = <{iri}>)
                }}
            }}"#,
            graph = GRAPH_LINKS,
            iri = resource_iri.as_str(),
        );

        let mut links = Vec::new();
        if let QueryResults::Solutions(solutions) = self.query(&sparql)? {
            for solution in solutions {
                let solution = solution?;
                if let (
                    Some(Term::NamedNode(source)),
                    Some(Term::NamedNode(target)),
                    Some(Term::Literal(relation)),
                ) = (
                    solution.get("source"),
                    solution.get("target"),
                    solution.get("relation"),
                ) {
                    links.push(LinkInfo {
                        source: source.clone(),
                        target: target.clone(),
                        relation: relation.value().to_string(),
                    });
                }
            }
        }

        Ok(links)
    }

    // ================================================================
    // Recall — multi-hop traversal for context retrieval
    // ================================================================

    /// Recall all relevant context starting from a resource.
    /// Returns the resource's own properties plus linked resources (1 hop)
    /// and concepts.
    pub fn recall(
        &self,
        resource_iri: &NamedNode,
        graph_id: &str,
        depth: u32,
    ) -> Result<RecallResult, StoreError> {
        let props = self.get_resource_properties(resource_iri, graph_id)?;
        let model = {
            let graph = namespaces::resource_graph_iri(graph_id);
            self.get_resource_type(resource_iri, &graph)?
        };

        let links = self.get_links_for(resource_iri)?;

        let mut linked_resources = Vec::new();
        for link in &links {
            let other = if link.source.as_str() == resource_iri.as_str() {
                &link.target
            } else {
                &link.source
            };

            // Try to get properties of the linked resource
            if let Some((other_id, _)) = self.find_resource_by_iri(other)? {
                let other_props = self.get_resource_properties(other, &other_id)?;
                let other_graph = namespaces::resource_graph_iri(&other_id);
                let other_model = self.get_resource_type(other, &other_graph).unwrap_or_default();
                linked_resources.push(LinkedResource {
                    iri: other.clone(),
                    model: other_model,
                    relation: link.relation.clone(),
                    direction: if link.source.as_str() == resource_iri.as_str() {
                        "outgoing".to_string()
                    } else {
                        "incoming".to_string()
                    },
                    properties: other_props,
                });
            }
        }

        // If depth > 1, recurse into linked resources
        let mut second_hop = Vec::new();
        if depth > 1 {
            for lr in &linked_resources {
                if let Some((_lr_id, _)) = self.find_resource_by_iri(&lr.iri)? {
                    let lr_links = self.get_links_for(&lr.iri)?;
                    for ll in lr_links {
                        let other = if ll.source.as_str() == lr.iri.as_str() {
                            &ll.target
                        } else {
                            &ll.source
                        };
                        // Skip if it's the original resource
                        if other.as_str() == resource_iri.as_str() {
                            continue;
                        }
                        if let Some((other_id, _)) = self.find_resource_by_iri(other)? {
                            let other_props = self.get_resource_properties(other, &other_id)?;
                            let other_graph = namespaces::resource_graph_iri(&other_id);
                            let other_model = self.get_resource_type(other, &other_graph).unwrap_or_default();
                            second_hop.push(LinkedResource {
                                iri: other.clone(),
                                model: other_model,
                                relation: ll.relation.clone(),
                                direction: format!(
                                    "via {}",
                                    lr.properties
                                        .get("name")
                                        .or(lr.properties.get("label"))
                                        .unwrap_or(&lr.iri.as_str().to_string())
                                ),
                                properties: other_props,
                            });
                        }
                    }
                }
            }
        }

        linked_resources.extend(second_hop);

        Ok(RecallResult {
            iri: resource_iri.clone(),
            model,
            properties: props,
            linked: linked_resources,
        })
    }

    /// Find a resource by its IRI (search across all resource graphs).
    pub fn find_resource_by_iri(
        &self,
        iri: &NamedNode,
    ) -> Result<Option<(String, NamedNode)>, StoreError> {
        let sparql = format!(
            r#"SELECT ?g WHERE {{
                GRAPH ?g {{
                    <{iri}> rdf:type ?type .
                }}
                FILTER(STRSTARTS(STR(?g), "{base}"))
            }} LIMIT 1"#,
            iri = iri.as_str(),
            base = namespaces::GRAPH_RESOURCE_BASE,
        );

        match self.query(&sparql)? {
            QueryResults::Solutions(mut solutions) => {
                if let Some(Ok(solution)) = solutions.next() {
                    if let Some(Term::NamedNode(graph)) = solution.get("g") {
                        let id = graph
                            .as_str()
                            .strip_prefix(namespaces::GRAPH_RESOURCE_BASE)
                            .unwrap_or(graph.as_str())
                            .to_string();
                        return Ok(Some((id, iri.clone())));
                    }
                }
                Ok(None)
            }
            _ => Ok(None),
        }
    }

    // ================================================================
    // Soft delete
    // ================================================================

    /// Soft-delete a resource by marking it as invalidated.
    pub fn forget_resource(
        &self,
        resource_iri: &NamedNode,
        graph_id: &str,
        reason: &str,
    ) -> Result<(), StoreError> {
        let graph = namespaces::resource_graph_iri(graph_id);
        let graph_name = GraphName::NamedNode(graph);

        self.store.insert(&Quad::new(
            resource_iri.clone(),
            namespaces::named_node(MEM, "invalidated"),
            Literal::new_typed_literal(
                "true",
                NamedNode::new(format!("{}boolean", crate::namespaces::XSD)).unwrap(),
            ),
            graph_name.clone(),
        ))?;
        self.store.insert(&Quad::new(
            resource_iri.clone(),
            namespaces::named_node(MEM, "invalidatedAt"),
            util::now_literal(),
            graph_name.clone(),
        ))?;
        self.store.insert(&Quad::new(
            resource_iri.clone(),
            namespaces::named_node(MEM, "invalidationReason"),
            Literal::new_simple_literal(reason),
            graph_name,
        ))?;

        Ok(())
    }

    // ================================================================
    // SPARQL query passthrough
    // ================================================================

    pub fn query(&self, sparql: &str) -> Result<QueryResults<'_>, StoreError> {
        let full_query = format!("{SPARQL_PREFIXES}\n{sparql}");
        let results = SparqlEvaluator::new()
            .parse_query(&full_query)?
            .on_store(&self.store)
            .execute()?;
        Ok(results)
    }

    pub fn update(&self, sparql: &str) -> Result<(), StoreError> {
        let full_update = format!("{SPARQL_PREFIXES}\n{sparql}");
        SparqlEvaluator::new()
            .parse_update(&full_update)?
            .on_store(&self.store)
            .execute()?;
        Ok(())
    }
}

// ================================================================
// Data types
// ================================================================

pub struct LinkInfo {
    pub source: NamedNode,
    pub target: NamedNode,
    pub relation: String,
}

pub struct LinkedResource {
    pub iri: NamedNode,
    pub model: String,
    pub relation: String,
    pub direction: String,
    pub properties: HashMap<String, String>,
}

pub struct RecallResult {
    pub iri: NamedNode,
    pub model: String,
    pub properties: HashMap<String, String>,
    pub linked: Vec<LinkedResource>,
}
