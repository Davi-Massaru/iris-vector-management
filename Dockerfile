FROM containers.intersystems.com/intersystems/iris-community@sha256:0a4d11a144f6510aa5d1fb41dc2498b7d705924860de3c0db2c1809b3f092657

ARG WITH_FIXTURES=1
USER root
COPY requirements-fixtures.txt /tmp/vector-requirements.txt
RUN if [ "$WITH_FIXTURES" = "1" ]; then python3 -m pip install --no-cache-dir --target /usr/irissys/mgr/python --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/vector-requirements.txt; fi
WORKDIR /usr/irissys/csp/vector-admin
COPY requirements-seeder.txt /tmp/vector-seeder-requirements.txt
RUN python3 -m pip install --no-cache-dir --target /usr/irissys/mgr/python -r /tmp/vector-seeder-requirements.txt
COPY --chown=irisowner:irisowner . .
RUN chmod +x tools/build-install.sh tools/set-system-password.sh
USER irisowner
ENV VECTOR_ADMIN_NAMESPACE=USER VECTOR_ADMIN_NAMESPACES=USER
RUN VECTOR_ADMIN_SEED=$WITH_FIXTURES sh tools/build-install.sh
EXPOSE 52773
WORKDIR /home/irisowner
# The inherited iris-main entrypoint runs IRIS and its bundled Web Gateway.
CMD ["--check-caps", "false"]
