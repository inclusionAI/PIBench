import 'package:dio/dio.dart';

//models
import '../../models/movie_model.dart';
import '../../models/movie_role_model.dart';
import '../../enums/movie_type_enum.dart';

//services
import '../networking/api_endpoint.dart';
import '../networking/api_service.dart';
import 'movie_fallback_data.dart';

//helpers
import '../../helper/typedefs.dart';

class MoviesRepository {
  final ApiService _apiService;
  final CancelToken? _cancelToken;

  MoviesRepository({
    required ApiService apiService,
    CancelToken? cancelToken,
  })  : _apiService = apiService,
        _cancelToken = cancelToken;

  Future<int> create({
    required JSON data,
  }) async {
    return await _apiService.setData<int>(
      endpoint: ApiEndpoint.movies(MovieEndpoint.BASE),
      data: data,
      cancelToken: _cancelToken,
      converter: (response) => response['body']['movie_id'] as int,
    );
  }

  Future<String> update({
    required int movieId,
    required JSON data,
  }) async {
    return await _apiService.updateData<String>(
      endpoint: ApiEndpoint.movies(MovieEndpoint.BY_ID, id: movieId),
      data: data,
      cancelToken: _cancelToken,
      converter: (response) => response['headers']['message'] as String,
    );
  }

  Future<String> delete({
    required int movieId,
    JSON? data,
  }) async {
    return await _apiService.deleteData<String>(
      endpoint: ApiEndpoint.movies(MovieEndpoint.BY_ID, id: movieId),
      data: data,
      cancelToken: _cancelToken,
      converter: (response) => response['headers']['message'] as String,
    );
  }

  Future<List<MovieModel>> fetchAll({
    JSON? queryParameters,
  }) async {
    try {
      return await _apiService.getCollectionData<MovieModel>(
        endpoint: ApiEndpoint.movies(MovieEndpoint.BASE),
        queryParams: queryParameters,
        cancelToken: _cancelToken,
        converter: (responseBody) => MovieModel.fromJson(responseBody),
      ).timeout(
        const Duration(seconds: 6),
        onTimeout: () => MovieFallbackData.all(movieType: _movieTypeFromQuery(queryParameters)),
      );
    } on Exception {
      return MovieFallbackData.all(movieType: _movieTypeFromQuery(queryParameters));
    }
  }

  MovieType? _movieTypeFromQuery(JSON? queryParameters) {
    final movieTypeValue = queryParameters?['movie_type'] as String?;
    if (movieTypeValue == null) return null;
    return MovieType.values.firstWhere(
      (value) => value.toJson == movieTypeValue,
      orElse: () => MovieType.ALL_MOVIES,
    );
  }

  Future<MovieModel> fetchOne({
    required int movieId,
  }) async {
    return await _apiService.getDocumentData<MovieModel>(
      endpoint: ApiEndpoint.movies(MovieEndpoint.BY_ID, id: movieId),
      cancelToken: _cancelToken,
      converter: (responseBody) => MovieModel.fromJson(responseBody),
    );
  }

  Future<List<MovieRoleModel>> fetchMovieRoles({
    required int movieId,
  }) async {
    return await _apiService.getCollectionData<MovieRoleModel>(
      endpoint: ApiEndpoint.movies(MovieEndpoint.ROLES, id: movieId),
      cancelToken: _cancelToken,
      converter: (responseBody) => MovieRoleModel.fromJson(responseBody),
    );
  }

  void cancelRequests() {
    _apiService.cancelRequests(cancelToken: _cancelToken);
  }
}
