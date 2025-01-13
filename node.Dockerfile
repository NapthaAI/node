FROM condaforge/miniforge3:24.9.2-0

WORKDIR /app
COPY . .

# use bash instead of sh
SHELL ["/bin/bash", "-c"]


# install deps
RUN apt-get update
RUN apt-get install curl gcc -y

# add conda install to path; use base environment
ENV PATH="/opt/conda/bin:${PATH}"
RUN conda create -n node python=3.12
RUN echo "source activate node" > /root/.bashrc
ENV PATH="/opt/conda/envs/node/bin:$PATH"
RUN echo

# set up poetry
ENV PATH="/root/.local/share/pypoetry/venv/bin/:${PATH}"
RUN pip install poetry
RUN poetry config virtualenvs.in-project true
RUN poetry lock
RUN poetry install --only main


EXPOSE 7001

# run db migrations / config & server
CMD poetry run python node/storage/db/init_db.py && \
    poetry run python node/storage/surreal && \
    poetry run python -m node.server.server --server-type http --port 7001
