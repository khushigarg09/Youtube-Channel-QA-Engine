from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from app.config import settings

_embeddings = None

def get_embeddings():
    """
    Initializes and caches the HuggingFace BGE embedding model.
    """
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    model_name = settings.EMBEDDING_MODEL
    model_kwargs = {"device": "cpu"}
    
    # Try to use CUDA if available
    try:
        import torch
        if torch.cuda.is_available():
            model_kwargs["device"] = "cuda"
    except ImportError:
        pass

    encode_kwargs = {"normalize_embeddings": True}
    
    # BAAI/bge-large-en-v1.5 query instruction for retrieval tasks
    _embeddings = HuggingFaceBgeEmbeddings(
        model_name=model_name,
        model_kwargs=model_kwargs,
        encode_kwargs=encode_kwargs,
        query_instruction="Represent this sentence for searching relevant passages:"
    )
    
    return _embeddings
