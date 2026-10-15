FROM docker.io/library/python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# The corpus comes from the vtk-pipelines-knowledge image, mounted at /kb (an image
# mount shows the image root there, so the corpus is /kb/knowledge); the decision log
# lives in /state.
ENV PW_KNOWLEDGE_DIR=/kb/knowledge PW_STATE_DIR=/state
VOLUME /state
EXPOSE 9101

ENTRYPOINT ["pipelines-watch"]
CMD ["watch"]
