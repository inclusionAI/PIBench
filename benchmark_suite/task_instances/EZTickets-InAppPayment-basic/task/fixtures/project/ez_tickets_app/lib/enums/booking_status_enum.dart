import 'package:freezed_annotation/freezed_annotation.dart';
// ignore_for_file: constant_identifier_names

/// A collection of statuses that bookings can have.
@JsonEnum()
enum BookingStatus {
  @JsonValue('reserved')
  RESERVED,
  @JsonValue('confirmed')
  CONFIRMED,
  @JsonValue('cancelled')
  CANCELLED,
}

/// A utility with extensions for enum name and serialized value.
extension ExtBookingStatus on BookingStatus {
  String get toJson {
    switch (this) {
      case BookingStatus.RESERVED:
        return 'reserved';
      case BookingStatus.CONFIRMED:
        return 'confirmed';
      case BookingStatus.CANCELLED:
        return 'cancelled';
    }
  }

  String get displayName {
    switch (this) {
      case BookingStatus.RESERVED:
        return 'Reserved';
      case BookingStatus.CANCELLED:
        return 'Cancelled';
      case BookingStatus.CONFIRMED:
        return 'Booked';
    }
  }

  bool get isCancelled {
    switch (this) {
      case BookingStatus.RESERVED:
        return false;
      case BookingStatus.CANCELLED:
        return true;
      case BookingStatus.CONFIRMED:
        return false;
    }
  }

  bool get canCancel {
    switch (this) {
      case BookingStatus.RESERVED:
        return true;
      case BookingStatus.CONFIRMED:
        return true;
      case BookingStatus.CANCELLED:
        return false;
    }
  }
}
