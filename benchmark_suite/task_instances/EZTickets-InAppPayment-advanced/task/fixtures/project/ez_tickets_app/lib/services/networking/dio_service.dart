import 'dart:async';

import 'package:dio/dio.dart';

//Exceptions
import 'network_exception.dart';

//helpers
import '../../helper/typedefs.dart';

/// A service class that wraps the [Dio] instance and provides methods for
/// basic network requests.
class DioService {
  /// An instance of [Dio] for executing network requests.
  late final Dio _dio;

  /// An instance of [CancelToken] used to pre-maturely cancel
  /// network requests.
  late final CancelToken _cancelToken;

  /// A public constructor that is used to create a Dio service and initialize
  /// the underlying [Dio] client.
  ///
  /// Attaches any external [Interceptor]s to the underlying [_dio] client.
  DioService({required Dio dioClient, Iterable<Interceptor>? interceptors})
  : _dio = dioClient, _cancelToken = CancelToken() {
    if (interceptors != null) _dio.interceptors.addAll(interceptors);
  }

  /// This method invokes the [cancel()] method on either the input
  /// [cancelToken] or internal [_cancelToken] to pre-maturely end all
  /// requests attached to this token.
  void cancelRequests({CancelToken? cancelToken}) {
    if (cancelToken == null) {
      _cancelToken.cancel('Cancelled');
    } else {
      cancelToken.cancel();
    }
  }

  bool _isRetryable(DioError error) {
    final statusCode = error.response?.statusCode;
    return error.type == DioErrorType.connectTimeout ||
        error.type == DioErrorType.receiveTimeout ||
        error.type == DioErrorType.sendTimeout ||
        error.type == DioErrorType.other ||
        statusCode == 408 ||
        statusCode == 429 ||
        (statusCode != null && statusCode >= 500);
  }

  Future<Response<JSON>> _withRetry(
    Future<Response<JSON>> Function() request,
  ) async {
    const delays = <Duration>[
      Duration.zero,
      Duration(milliseconds: 700),
      Duration(seconds: 2),
    ];

    for (var attempt = 0; attempt < delays.length; attempt++) {
      if (delays[attempt] != Duration.zero) {
        await Future<void>.delayed(delays[attempt]);
      }

      try {
        return await request();
      } on DioError catch (error) {
        final isLastAttempt = attempt == delays.length - 1;
        if (isLastAttempt || !_isRetryable(error)) rethrow;
      }
    }

    throw StateError('Retry loop exited unexpectedly');
  }

  /// This method sends a `GET` request to the [endpoint] and returns the
  /// **decoded** response.
  ///
  /// Any errors encountered during the request are caught and a custom
  /// [NetworkException] is thrown.
  ///
  /// [queryParams] holds any query parameters for the request.
  ///
  /// [cancelToken] is used to cancel the request pre-maturely. If null,
  /// the **default** [cancelToken] inside [DioService] is used.
  ///
  /// [options] are special instructions that can be merged with the request.
  Future<JSON> get({
    required String endpoint,
    JSON? queryParams,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _withRetry(
        () => _dio.get<JSON>(
          endpoint,
          queryParameters: queryParams,
          options: options,
          cancelToken: cancelToken ?? _cancelToken,
        ),
      );
      return response.data as JSON;
    } on Exception catch (ex) {
      throw NetworkException.getDioException(ex);
    }
  }

  /// This method sends a `POST` request to the [endpoint] and returns the
  /// **decoded** response.
  ///
  /// Any errors encountered during the request are caught and a custom
  /// [NetworkException] is thrown.
  ///
  /// The [data] contains body for the request.
  ///
  /// [cancelToken] is used to cancel the request pre-maturely. If null,
  /// the **default** [cancelToken] inside [DioService] is used.
  ///
  /// [options] are special instructions that can be merged with the request.
  Future<JSON> post({
    required String endpoint,
    JSON? data,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _withRetry(
        () => _dio.post<JSON>(
          endpoint,
          data: data,
          options: options,
          cancelToken: cancelToken ?? _cancelToken,
        ),
      );
      return response.data as JSON;
    } on Exception catch (ex) {
      throw NetworkException.getDioException(ex);
    }
  }

  /// This method sends a `PATCH` request to the [endpoint] and returns the
  /// **decoded** response.
  ///
  /// Any errors encountered during the request are caught and a custom
  /// [NetworkException] is thrown.
  ///
  /// The [data] contains body for the request.
  ///
  /// [cancelToken] is used to cancel the request pre-maturely. If null,
  /// the **default** [cancelToken] inside [DioService] is used.
  ///
  /// [options] are special instructions that can be merged with the request.
  Future<JSON> patch({
    required String endpoint,
    JSON? data,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _withRetry(
        () => _dio.put<JSON>(
          endpoint,
          data: data,
          options: options,
          cancelToken: cancelToken ?? _cancelToken,
        ),
      );
      return response.data as JSON;
    } on Exception catch (ex) {
      throw NetworkException.getDioException(ex);
    }
  }

  /// This method sends a `DELETE` request to the [endpoint] and returns the
  /// **decoded** response.
  ///
  /// Any errors encountered during the request are caught and a custom
  /// [NetworkException] is thrown.
  ///
  /// The [data] contains body for the request.
  ///
  /// [cancelToken] is used to cancel the request pre-maturely. If null,
  /// the **default** [cancelToken] inside [DioService] is used.
  ///
  /// [options] are special instructions that can be merged with the request.
  Future<JSON> delete({
    required String endpoint,
    JSON? data,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _withRetry(
        () => _dio.delete<JSON>(
          endpoint,
          data: data,
          options: options,
          cancelToken: cancelToken ?? _cancelToken,
        ),
      );
      return response.data as JSON;
    } on Exception catch (ex) {
      throw NetworkException.getDioException(ex);
    }
  }
}
