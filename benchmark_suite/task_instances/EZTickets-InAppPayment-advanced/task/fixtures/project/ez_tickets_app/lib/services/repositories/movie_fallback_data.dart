import '../../enums/movie_type_enum.dart';
import '../../models/genre_model.dart';
import '../../models/movie_model.dart';

class MovieFallbackData {
  const MovieFallbackData._();

  static List<MovieModel> all({MovieType? movieType}) {
    final movies = <MovieModel>[
      MovieModel(
        movieId: 4,
        title: 'GODZILLA VS KONG',
        summary: 'Legends collide as Godzilla and Kong clash on the big screen.',
        year: 2021,
        rating: 6.5,
        trailerUrl: 'https://media.publit.io/file/h_720/godzilla_vs_kong.mp4',
        posterUrl: 'https://images.squarespace-cdn.com/content/v1/51b3dc8ee4b051b96ceb10de/1615997337403-G2AT6OCZ0LD8VLQ1IHGC/EwnOBogWEAEiakT.jpeg?format=1500w',
        movieType: MovieType.NOW_SHOWING,
        genres: const [
          GenreModel(genreId: 1, genre: 'Horror'),
          GenreModel(genreId: 2, genre: 'Action'),
          GenreModel(genreId: 4, genre: 'Comedy'),
        ],
      ),
      MovieModel(
        movieId: 34,
        title: 'JOKER',
        summary: 'Arthur Fleck is shunned by society and embraces chaos.',
        year: 2019,
        rating: 8.4,
        trailerUrl: 'https://media.publit.io/file/h_720/joker-x.mp4',
        posterUrl: 'https://pbs.twimg.com/media/EA4LLfsW4AErVjR.jpg',
        movieType: MovieType.NOW_SHOWING,
        genres: const [
          GenreModel(genreId: 5, genre: 'Drama'),
          GenreModel(genreId: 6, genre: 'Thriller'),
          GenreModel(genreId: 11, genre: 'Crime'),
        ],
      ),
      MovieModel(
        movieId: 35,
        title: 'SUICIDE SQUAD 2',
        summary: 'A team of dangerous supervillains is sent on a mission.',
        year: 2021,
        trailerUrl: 'https://media.publit.io/file/h_720/suicide_squad.mp4',
        posterUrl: 'https://www.inspirationde.com/media/2019/08/cristiano-siqueira-on-behance-1565929796gk84n.png',
        movieType: MovieType.COMING_SOON,
        genres: const [
          GenreModel(genreId: 2, genre: 'Action'),
          GenreModel(genreId: 3, genre: 'Fantasy'),
          GenreModel(genreId: 4, genre: 'Comedy'),
        ],
      ),
      MovieModel(
        movieId: 36,
        title: 'THE BATMAN',
        summary: 'The Riddler plays a deadly game in Gotham City.',
        year: 2022,
        trailerUrl: 'https://media.publit.io/file/h_720/batman.mp4',
        posterUrl: 'https://www.inspirationde.com/media/2020/08/the-batman-poster-by-mizuriofficial-on-deviantart-15987584958gkn4.jpg',
        movieType: MovieType.COMING_SOON,
        genres: const [
          GenreModel(genreId: 2, genre: 'Action'),
          GenreModel(genreId: 5, genre: 'Drama'),
          GenreModel(genreId: 11, genre: 'Crime'),
        ],
      ),
    ];

    if (movieType == null || movieType == MovieType.ALL_MOVIES) return movies;
    return movies.where((movie) => movie.movieType == movieType).toList();
  }
}
