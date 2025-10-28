"""Tool implementations for the SAM RAG plugin."""

import logging
from typing import Dict, Any, Optional, List
import os
import uuid
import tempfile
import asyncio
import datetime
import mimetypes
import base64 
import inspect
import json
from urllib.parse import urlparse, parse_qs

from google.adk.tools import ToolContext

from solace_agent_mesh.agent.utils.artifact_helpers import load_artifact_content_or_metadata
from solace_agent_mesh.common.utils.mime_helpers import is_text_based_mime_type

# Import decorator for embed resolution
from solace_agent_mesh.agent.utils.artifact_helpers import save_artifact_with_metadata
from solace_agent_mesh.agent.utils.context_helpers import get_original_session_id

log = logging.getLogger(__name__)

async def ingest_document(
    input_file: str,
    tool_context: ToolContext = None,
    tool_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Ingest a file into the RAG system or vector database.
    
    Args:
        input_file: The filename (and :version) of the input artifact from artifact service. The file can be a PDF, TXT, etc file. The file is the original document to be ingested.
        tool_context: The context provided by the ADK framework.
        tool_config: Optional tool configuration.
        
    Returns:
        A dictionary containing the status of the ingestion operation.
    """
    if not tool_context:
        return {
            "status": "error",
            "error_message": "ToolContext is missing, cannot ingest document.",
        }

    inv_context = tool_context._invocation_context
    log_identifier = f"[RAGIngestTool:{inv_context.agent.name}]"
    log.info("%s Ingesting document from file: %s", log_identifier, input_file)
    
    # Access host_component via tool_context for services not related to artifact saving
    host_component = getattr(inv_context.agent, "host_component", None)
    if not host_component:
        log.error("%s Host component not found, cannot access RAG services.", log_identifier)
        return {
            "status": "error",
            "error_message": "Host component not found, cannot access RAG services.",
        }
    
    # Get file tracker from agent_specific_state
    file_tracker = host_component.get_agent_specific_state("file_tracker")
    if not file_tracker:
        log.error("%s File tracker not found in agent_specific_state.", log_identifier)
        return {
            "status": "error",
            "error_message": "File tracker not found in agent_specific_state.",
        }
    
    # Get artifact service directly from tool_context's invocation_context
    artifact_service = inv_context.artifact_service
    if not artifact_service:
        log.warning("%s ArtifactService not available in tool_context. Original documents will not be stored as artifacts.", log_identifier)
    
    try:
        # Parse filename and version from input_file (e.g., "myfile.pdf:2")
        parts = input_file.split(":", 1)
        filename_base_for_load = parts[0]
        version_str = parts[1] if len(parts) > 1 else None
        version_to_load = int(version_str) if version_str else None
        log.debug("%s Parsed input file '%s' to base filename '%s' and version %s", log_identifier, input_file, filename_base_for_load, version_to_load)
        
        # Get app_name, user_id, and session_id from invocation context
        app_name = inv_context.app_name
        user_id = inv_context.user_id or "default_user"
        original_session_id = get_original_session_id(inv_context)
        
        # Get latest version if not specified
        if version_to_load is None:
            log.debug("%s No version specified for input '%s'. Attempting to load latest version.", log_identifier, filename_base_for_load)
            list_versions_method = getattr(artifact_service, 'list_versions')
            log.debug("%s Using method '%s' to list versions for app '%s'. session_id: %s, user_id: %s", log_identifier, list_versions_method.__name__, app_name, original_session_id, user_id)
            if inspect.iscoroutinefunction(list_versions_method):
                versions = await list_versions_method(app_name=app_name, user_id=user_id, session_id=original_session_id, filename=filename_base_for_load)
            else:
                versions = await asyncio.to_thread(list_versions_method, app_name=app_name, user_id=user_id, session_id=original_session_id, filename=filename_base_for_load)
            if not versions:
                raise FileNotFoundError(f"Artifact '{filename_base_for_load}' not found.")
            version_to_load = max(versions)
            log.debug("%s Using latest version for input: %d", log_identifier, version_to_load)
        
        # Load metadata to get original filename and extension
        metadata_filename_to_load = f"{filename_base_for_load}.metadata.json"
        try:
            log.debug("%s Attempting to load metadata for '%s' v%s", log_identifier, filename_base_for_load, version_to_load)
            load_meta_method = getattr(artifact_service, 'load_artifact')
            if inspect.iscoroutinefunction(load_meta_method):
                metadata_part = await load_meta_method(app_name=app_name, user_id=user_id, session_id=original_session_id, filename=metadata_filename_to_load, version=version_to_load)
            else:
                metadata_part = await asyncio.to_thread(load_meta_method, app_name=app_name, user_id=user_id, session_id=original_session_id, filename=metadata_filename_to_load, version=version_to_load)
            if not metadata_part or not metadata_part.inline_data:
                log.warning("%s Metadata for '%s' v%s not found. Using input filename for naming.", log_identifier, filename_base_for_load, version_to_load)
                raise FileNotFoundError(f"Metadata for '{filename_base_for_load}' v{version_to_load} not found.")
            input_metadata = json.loads(metadata_part.inline_data.data.decode("utf-8"))
            log.debug("%s Loaded metadata for '%s' v%s: %s", log_identifier, filename_base_for_load, version_to_load, input_metadata)
            original_input_filename_from_meta = input_metadata.get("filename", filename_base_for_load)
            original_input_basename, original_input_ext = os.path.splitext(original_input_filename_from_meta)
        except Exception as meta_err:
            log.warning("%s Could not load metadata for '%s' v%s: %s. Using input filename for naming.", log_identifier, filename_base_for_load, version_to_load, meta_err)
            original_input_basename, original_input_ext = os.path.splitext(filename_base_for_load)
        
        # Load actual artifact content
        log.debug("%s Attempting to load artifact content for '%s', %s, %s, %s, %s", log_identifier, app_name, user_id, original_session_id, filename_base_for_load, version_to_load)
        load_artifact_method = getattr(artifact_service, 'load_artifact')
        if inspect.iscoroutinefunction(load_artifact_method):
            input_artifact_part = await load_artifact_method(app_name=app_name, user_id=user_id, session_id=original_session_id, filename=filename_base_for_load, version=version_to_load)
        else:
            input_artifact_part = await asyncio.to_thread(load_artifact_method, app_name=app_name, user_id=user_id, session_id=original_session_id, filename=filename_base_for_load, version=version_to_load)
   
        if not input_artifact_part or not input_artifact_part.inline_data:
            log.error("%s Content for '%s' v%s not found. Cannot ingest document.", log_identifier, filename_base_for_load, version_to_load)
            raise FileNotFoundError(f"Content for artifact '{filename_base_for_load}' v{version_to_load} not found.")
        input_bytes = input_artifact_part.inline_data.data

        # Determine MIME type
        mime_type = input_metadata.get("mime_type") if 'input_metadata' in locals() else mimetypes.guess_type(final_name)[0] or "application/octet-stream"
        log.debug("%s Detected MIME type for '%s': %s", log_identifier, filename_base_for_load, mime_type)
        
        # Create temporary file with content
        log.debug("%s Writing input artifact content to temporary file.", log_identifier)
        temp_suffix = original_input_ext if original_input_ext else None
        temp_input_file = tempfile.NamedTemporaryFile(delete=False, suffix=temp_suffix)
        temp_file_path = temp_input_file.name
        temp_input_file.write(input_bytes)
        temp_input_file.close()  # Close it so file_tracker can open it
        log.debug("%s Input artifact content written to temporary file: %s", log_identifier, temp_file_path)
        
        # Determine file name for RAG
        final_name = original_input_filename_from_meta if 'original_input_filename_from_meta' in locals() else os.path.basename(filename_base_for_load)
        
        # Get pipeline instance from host_component
        pipeline = host_component.get_agent_specific_state("rag_pipeline")
        if not pipeline:
            log.error("%s Pipeline not found in agent_specific_state.", log_identifier)
            return {
                "status": "error",
                "error_message": "Pipeline not found in agent_specific_state.",
            }
        
        # Create metadata for the document
        document_metadata = {
            "file_path": "",
            "file_type": mime_type,
            "file_name": final_name,  # Add file_name for reference in search results
            "source": "upload_file",
            "ingestion_timestamp": datetime.datetime.now().isoformat(),
        }

        # Create artifact URL for the document
        log.debug("Document metadata for RAG: %s", document_metadata)
        artifact_url = f"artifact://{app_name}/{user_id}/{original_session_id}/{final_name}?version={version_to_load}"
        document_metadata["artifact_url"] = artifact_url
        
        # Process the file through the complete RAG pipeline
        log.info("%s Processing file through RAG pipeline: %s", log_identifier, temp_file_path)
        pipeline_result = pipeline.process_files([temp_file_path], metadata=document_metadata)
        log.debug("%s Pipeline processing result: %s", log_identifier, pipeline_result)
        
        mime_type = document_metadata["file_type"]
        log.debug("%s Saving document as artifact in session %s", log_identifier, original_session_id)
        
        # Convert input_bytes to UTF-8 before saving
        if is_text_based_mime_type(mime_type):
            try:
                # Try to decode and re-encode to ensure valid UTF-8
                input_bytes = input_bytes.decode('utf-8')
                log.debug("%s Successfully converted input bytes to UTF-8", log_identifier)
            except UnicodeDecodeError:
                # If it's not valid UTF-8, keep the original bytes
                log.warning("%s Input bytes are not valid UTF-8, using original bytes", log_identifier)
            
        artifact_result = await save_artifact_with_metadata(
            artifact_service=artifact_service,
            app_name=app_name,
            user_id=user_id,
            session_id=original_session_id,
            filename=final_name,
            content_bytes=input_bytes,
            mime_type=mime_type,
            metadata_dict=document_metadata,
            timestamp=datetime.datetime.now()
        )
        
        log.info("%s Stored document as artifact in %s: %s", log_identifier, original_session_id, artifact_result)
        
        # Clean up temporary file
        try:
            os.unlink(temp_file_path)
            log.debug("%s Removed temporary file: %s", log_identifier, temp_file_path)
        except OSError as e_remove:
            log.error("%s Failed to remove temporary file %s: %s", log_identifier, temp_file_path, e_remove)
        
        # Prepare response based on pipeline result
        if pipeline_result.get("success", False):
            return {
                "status": "success",
                "message": f"Document '{final_name}' successfully ingested through RAG pipeline.",
                "document_ids": pipeline_result.get("document_ids", []),
                "artifact_url": artifact_url
            }
        else:
            log.warning("%s Pipeline processing failed: %s", log_identifier, pipeline_result.get("message", "Unknown error"))
            return {
                "status": "partial_success",
                "message": f"Document '{final_name}' stored but pipeline processing failed: {pipeline_result.get('message', 'Unknown error')}",
                "artifact_url": artifact_url
            }
            
    except FileNotFoundError as e:
        log.warning("%s File not found error: %s", log_identifier, e)
        return {"status": "error", "error_message": str(e)}
    except ValueError as e:
        log.warning("%s Value error: %s", log_identifier, e)
        return {"status": "error", "error_message": str(e)}
    except Exception as e:
        log.exception("%s Unexpected error in ingest_document: %s", log_identifier, e)
        return {"status": "error", "error_message": f"Failed to ingest document: {str(e)}"}

async def search_documents(
    query: str,
    filter_criteria: Optional[Dict[str, Any]] = None,
    include_original_documents: Optional[bool] = True,
    include_references: Optional[bool] = True,
    tool_context: ToolContext = None,
    tool_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Search for documents relevant to the query and retrieve the relevant content and references to documents.
    
    Args:
        query: The search query.
        filter_criteria: Optional criteria to filter search results.
        include_original_documents: Whether to include original documents as artifacts in the response.
        include_references: Whether to include document references in the response.
        tool_context: The context provided by the ADK framework.
        tool_config: Optional tool configuration.
        
    Returns:
        A dictionary containing the search results, augmented response, and document references.
    """
    if not tool_context:
        return {
            "status": "error",
            "error_message": "ToolContext is missing, cannot search documents.",
        }
    
    inv_context = tool_context._invocation_context
    log_identifier = f"[RAGSearchTool:{inv_context.agent.name}]"
    log.info("%s Searching documents. Query: %s", log_identifier, query)
    
    # Access host_component via tool_context for services not related to artifact saving
    host_component = getattr(inv_context.agent, "host_component", None)
    if not host_component: # For augmentation_handler
        return {
            "status": "error",
            "error_message": "Host component not found, cannot access RAG services.",
        }
    
    # Get augmentation handler from agent_specific_state
    augmentation_handler = host_component.get_agent_specific_state("augmentation_handler")
    if not augmentation_handler:
        return {
            "status": "error",
            "error_message": "Augmentation handler not found in agent_specific_state.",
        }
    
    # Get artifact service directly from tool_context's invocation_context
    artifact_service = inv_context.artifact_service
    if (include_original_documents or include_references) and not artifact_service:
        log.warning("%s ArtifactService not available in tool_context. Original documents and references cannot be included.", log_identifier)
        include_original_documents = False
        include_references = False
    
    try:
        # Get session ID and user_id from inv_context
        session_id_str = get_original_session_id(inv_context) 
        user_id = inv_context.user_id or "default_user" 
        app_name = inv_context.app_name
        
        # Get relevant chunks and content from vector database
        content, chunks = await augmentation_handler.augment(
            query,
            inv_context.session, # Pass the session object to augment
            filter=filter_criteria,
            return_chunks=True  # Make sure augment method returns the actual chunks
        )
        
        if not content:
            return {
                "status": "no_results",
                "message": "No relevant documents found for the query.",
            }
        
        # Prepare response structure
        response = {
            "status": "success",
            "augmented_response": content,
            "message": "Successfully retrieved and augmented relevant documents."
        }

        # Process chunks to include artifact_url and potentially retrieve content
        processed_chunks = []
        if chunks: # Ensure chunks is not None and not empty
            for chunk in chunks:
                if not chunk:
                    continue
                chunk_metadata = chunk.get("metadata", {})
                current_artifact_url = chunk_metadata.get("artifact_url")

                processed_chunk_data = {
                    "text": chunk.get("content"), # Text content of the chunk
                    "score": chunk.get("score"),
                    "metadata": chunk_metadata, # Original metadata, including filename, etc.
                    "artifact_url": current_artifact_url # Promote artifact_url for easier access
                }

                if current_artifact_url and artifact_service:
                    retrieved_info = {
                        "status": "pending",
                        "content_base64": None,
                        "mime_type": None,
                        "error_message": None,
                        "url_used": current_artifact_url,
                        "loaded_filename": None,
                        "loaded_version": None,
                    }
                    try:
                        if current_artifact_url.startswith("artifact://"):
                            parsed_url = urlparse(current_artifact_url)
                            # Filename is composed of the "authority" (netloc) and the path on that authority
                            filename_for_load = os.path.basename(parsed_url.path)
                            
                            version_param_for_load = None # Initialize
                            
                            # Try to get artifact version from query parameters
                            query_params_dict = parse_qs(parsed_url.query)
                            if 'version' in query_params_dict and query_params_dict['version']:
                                version_str_from_query = query_params_dict['version'][0]
                                try:
                                    version_param_for_load = int(version_str_from_query)
                                except ValueError:
                                    log.warning("%s Invalid version '%s' in query for %s. Assuming 'latest'.", log_identifier, version_str_from_query, current_artifact_url)
                                    version_param_for_load = "latest" # Treat invalid query version as "latest"

                            # Get latest version if not specified
                            if version_param_for_load is None:
                                log.debug("%s No version specified for input '%s'. Attempting to load latest version.", log_identifier, filename_for_load)
                                list_versions_method = getattr(artifact_service, 'list_versions')
                                log.debug("%s Using method '%s' to list versions for app '%s'. session_id: %s, user_id: %s", log_identifier, list_versions_method.__name__, app_name, session_id_str, user_id)
                                if inspect.iscoroutinefunction(list_versions_method):
                                    versions = await list_versions_method(app_name=app_name, user_id=user_id, session_id=session_id_str, filename=filename_for_load)
                                else:
                                    versions = await asyncio.to_thread(list_versions_method, app_name=app_name, user_id=user_id, session_id=session_id_str, filename=filename_for_load)
                                if not versions:
                                    raise FileNotFoundError(f"Artifact '{filename_for_load}' not found.")
                                version_param_for_load = max(versions)
                                log.debug("%s Using latest version for input: %d", log_identifier, version_param_for_load)
                                                        
                            retrieved_info["loaded_filename"] = filename_for_load
                            retrieved_info["loaded_version"] = str(version_param_for_load)

                            log.debug("%s Attempting to download artifact: %s version: %s", log_identifier, filename_for_load, version_param_for_load)

                            try:
                                # Signal downloading of the artifact
                                signal_key = f"temp:a2a_return_artifact:{uuid.uuid4().hex}"
                                tool_context.actions.state_delta[signal_key] = {
                                    "filename": filename_for_load,
                                    "version": version_param_for_load,
                                }
                                log.debug(
                                    "%s Signaled return request for '%s' v%d via state_delta key '%s'.",
                                    log_identifier,
                                    filename_for_load,
                                    version_param_for_load,
                                    signal_key,
                                )

                                retrieved_info["status"] = "success"
                                # log.debug("%s Successfully loaded artifact: %s v%d", log_identifier, filename_for_load, artifact_data.get('version'))
                            except Exception:
                                retrieved_info["status"] = "error"
                                retrieved_info["error_message"] = "Failed to load artifact."
                                log.warning("%s Failed to load artifact %s: %s", log_identifier, filename_for_load, retrieved_info['error_message'])

                        else:
                            retrieved_info["status"] = "unsupported_scheme"
                            retrieved_info["error_message"] = f"URL scheme for '{current_artifact_url}' is not 'artifact://'. Direct fetching not supported by this method."
                            log.warning("%s Unsupported artifact_url scheme for artifact_service loading: %s", log_identifier, current_artifact_url)
                    
                    except FileNotFoundError as fnf_error:
                        retrieved_info["status"] = "error"
                        retrieved_info["error_message"] = f"Artifact not found ({filename_for_load}): {str(fnf_error)}"
                        log.warning("%s Artifact not found via URL %s: %s", log_identifier, current_artifact_url, fnf_error)
                    except ValueError as val_error: # e.g. if version parsing fails badly, though handled above
                        retrieved_info["status"] = "error"
                        retrieved_info["error_message"] = f"Invalid artifact URL format or version ({current_artifact_url}): {str(val_error)}"
                        log.error("%s Invalid artifact URL format %s: %s", log_identifier, current_artifact_url, val_error)
                    except Exception as e:
                        retrieved_info["status"] = "error"
                        retrieved_info["error_message"] = f"Unexpected error loading artifact from {current_artifact_url}: {str(e)}"
                        log.exception("%s Unexpected error loading artifact %s: %s", log_identifier, current_artifact_url, e)

                    processed_chunk_data["retrieved_artifact_content"] = retrieved_info
                processed_chunks.append(processed_chunk_data)
        
        response["chunks"] = processed_chunks
        return response
        
    except Exception as e:
        log.exception("%s Error searching documents: %s", log_identifier, e)
        return {
            "status": "error",
            "error_message": f"Failed to search documents: {str(e)}",
        }
