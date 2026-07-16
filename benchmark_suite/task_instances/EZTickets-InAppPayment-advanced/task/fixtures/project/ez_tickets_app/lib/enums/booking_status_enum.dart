import 'package:freezed_annotation/freezed_annotation.dart';
// ignore_for_file: constant_identifier_names

/// A collection of statuses that bookings can have.
@JsonEnum()
enum BookingStatus {
  @JsonValue('confirmed')
  CONFIRMED,
  @JsonValue('cancelled')
  CANCELLED,
  @JsonValue('reserved')
  RESERVED,
}

/// A utility with extensions for enum name and serialized value.
extension ExtBookingStatus on BookingStatus {
  String get toJson => name.toLowerCase();

  String get displayName {
    switch (this) {
      case BookingStatus.CANCELLED:
        return 'Cancelled';
      case BookingStatus.CONFIRMED:
        return 'Booked';
      case BookingStatus.RESERVED:
        return 'Reserved';
    }
  }

  bool get isCancelled => this == BookingStatus.CANCELLED;

  bool get canCancel => this != BookingStatus.CANCELLED;
}
