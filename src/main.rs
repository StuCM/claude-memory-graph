mod namespaces;
mod ontology;
mod store;
mod tools;
mod util;

use std::path::PathBuf;
use std::sync::Arc;

use rmcp::ServiceExt;
use tracing_subscriber::EnvFilter;

use store::MemoryStore;
use tools::MemoryGraphServer;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            EnvFilter::from_default_env().add_directive(tracing::Level::INFO.into()),
        )
        .with_ansi(false)
        .init();

    let store_path = std::env::var("MEMORY_GRAPH_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            dirs::home_dir()
                .expect("Could not determine home directory")
                .join(".claude")
                .join("memory-graph")
                .join("store")
        });

    tracing::info!("Opening memory store at: {}", store_path.display());
    let store = Arc::new(MemoryStore::open_or_create(store_path)?);

    let server = MemoryGraphServer::new(store.clone());
    let service = server.serve(rmcp::transport::stdio()).await?;
    service.waiting().await?;

    // Save graph to disk on shutdown
    tracing::info!("Shutting down, saving graph...");
    store.save()?;

    Ok(())
}
