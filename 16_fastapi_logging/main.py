import uvicorn  # Import uvicorn server runner

from app.config import get_settings  # Import app settings loader


def main():  # Define the server startup function
    """Run the FastAPI application via uvicorn.

    Reads environment configuration to determine whether to enable hot-reloading
    and disables uvicorn's default log format to allow our unified structlog/Loguru
    pipeline to control console and file output.
    """
    settings = get_settings()  # Retrieve cached settings values from configuration loaders
    reload = not settings.is_production  # Enable hot-reloading in non-production development environments

    uvicorn.run(  # Start the uvicorn HTTP server engine
        "app.main:app",  # Specify the import path target module and FastAPI instance variable
        host="127.0.0.1",  # Configure server binding interface address (localhost loopback)
        port=8000,  # Configure binding port number 8000
        reload=reload,  # Set the hot-reloading configuration status boolean
        log_config=None,  # Pass log_config=None so Uvicorn does not overwrite custom structlog/Loguru sinks
    )


if __name__ == "__main__":  # Execute main only if file is run directly as script
    main()  # Run the main uvicorn bootstrapper function

