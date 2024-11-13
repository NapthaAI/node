# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2
from node.server import grpc_server_pb2 as grpc__server__pb2

GRPC_GENERATED_VERSION = '1.67.0'
GRPC_VERSION = grpc.__version__
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    raise RuntimeError(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in grpc_server_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class GrpcServerStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.is_alive = channel.unary_unary(
                '/agent.GrpcServer/is_alive',
                request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
                response_deserializer=grpc__server__pb2.GeneralResponse.FromString,
                _registered_method=True)
        self.stop = channel.unary_unary(
                '/agent.GrpcServer/stop',
                request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
                response_deserializer=grpc__server__pb2.GeneralResponse.FromString,
                _registered_method=True)
        self.CheckUser = channel.unary_unary(
                '/agent.GrpcServer/CheckUser',
                request_serializer=grpc__server__pb2.CheckUserRequest.SerializeToString,
                response_deserializer=grpc__server__pb2.CheckUserResponse.FromString,
                _registered_method=True)
        self.RegisterUser = channel.unary_unary(
                '/agent.GrpcServer/RegisterUser',
                request_serializer=grpc__server__pb2.RegisterUserRequest.SerializeToString,
                response_deserializer=grpc__server__pb2.RegisterUserResponse.FromString,
                _registered_method=True)
        self.RunAgent = channel.unary_stream(
                '/agent.GrpcServer/RunAgent',
                request_serializer=grpc__server__pb2.RunAgentRequest.SerializeToString,
                response_deserializer=grpc__server__pb2.RunAgentResponse.FromString,
                _registered_method=True)


class GrpcServerServicer(object):
    """Missing associated documentation comment in .proto file."""

    def is_alive(self, request, context):
        """check server is alive
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def stop(self, request, context):
        """stop the server
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CheckUser(self, request, context):
        """check user
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def RegisterUser(self, request, context):
        """register user
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def RunAgent(self, request, context):
        """run agent
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_GrpcServerServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'is_alive': grpc.unary_unary_rpc_method_handler(
                    servicer.is_alive,
                    request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
                    response_serializer=grpc__server__pb2.GeneralResponse.SerializeToString,
            ),
            'stop': grpc.unary_unary_rpc_method_handler(
                    servicer.stop,
                    request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
                    response_serializer=grpc__server__pb2.GeneralResponse.SerializeToString,
            ),
            'CheckUser': grpc.unary_unary_rpc_method_handler(
                    servicer.CheckUser,
                    request_deserializer=grpc__server__pb2.CheckUserRequest.FromString,
                    response_serializer=grpc__server__pb2.CheckUserResponse.SerializeToString,
            ),
            'RegisterUser': grpc.unary_unary_rpc_method_handler(
                    servicer.RegisterUser,
                    request_deserializer=grpc__server__pb2.RegisterUserRequest.FromString,
                    response_serializer=grpc__server__pb2.RegisterUserResponse.SerializeToString,
            ),
            'RunAgent': grpc.unary_stream_rpc_method_handler(
                    servicer.RunAgent,
                    request_deserializer=grpc__server__pb2.RunAgentRequest.FromString,
                    response_serializer=grpc__server__pb2.RunAgentResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'agent.GrpcServer', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('agent.GrpcServer', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class GrpcServer(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def is_alive(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/agent.GrpcServer/is_alive',
            google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            grpc__server__pb2.GeneralResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def stop(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/agent.GrpcServer/stop',
            google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            grpc__server__pb2.GeneralResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CheckUser(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/agent.GrpcServer/CheckUser',
            grpc__server__pb2.CheckUserRequest.SerializeToString,
            grpc__server__pb2.CheckUserResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def RegisterUser(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/agent.GrpcServer/RegisterUser',
            grpc__server__pb2.RegisterUserRequest.SerializeToString,
            grpc__server__pb2.RegisterUserResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def RunAgent(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(
            request,
            target,
            '/agent.GrpcServer/RunAgent',
            grpc__server__pb2.RunAgentRequest.SerializeToString,
            grpc__server__pb2.RunAgentResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
