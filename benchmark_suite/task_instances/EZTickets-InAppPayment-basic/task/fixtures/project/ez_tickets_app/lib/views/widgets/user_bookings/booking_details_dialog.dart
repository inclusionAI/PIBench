import 'package:flutter/material.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';

//Helpers
import '../../../enums/booking_status_enum.dart';
import '../../../helper/utils/constants.dart';

//Models
import '../../../models/booking_model.dart';

//Providers
import '../../../providers/all_providers.dart';
import '../../../providers/bookings_provider.dart';

//Skeletons
import '../../skeletons/movie_poster_placeholder.dart';

//Widgets
import '../common/custom_dialog.dart';
import '../common/custom_network_image.dart';
import '../common/tappable_icon.dart';

class BookingDetailsDialog extends ConsumerWidget {
  final String posterUrl;
  final List<BookingModel> bookings;

  const BookingDetailsDialog({
    Key? key,
    required this.posterUrl,
    required this.bookings,
  }) : super(key: key);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Center(
      child: SizedBox(
        height: 420,
        width: 280,
        child: Column(
          children: [
            //Movie Image
            CustomNetworkImage(
              imageUrl: posterUrl,
              fit: BoxFit.cover,
              height: 120,
              borderRadius: const BorderRadius.only(
                topRight: Radius.circular(20),
                topLeft: Radius.circular(20),
              ),
              placeholder: const MoviePosterPlaceholder(),
              errorWidget: const MoviePosterPlaceholder(),
            ),

            //Grey Container
            Expanded(
              child: Material(
                color: Constants.scaffoldColor,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(15, 12, 15, 0),
                  child: Column(
                    children: [
                      //Column Labels
                      Row(
                        children: const [
                          //Seat label
                          SizedBox(
                            width: 50,
                            child: Text(
                              'Seat',
                              style: TextStyle(
                                color: Constants.textWhite80Color,
                              ),
                            ),
                          ),

                          //Price label
                          Expanded(
                            child: Text(
                              'Price',
                              style: TextStyle(
                                color: Constants.textWhite80Color,
                              ),
                            ),
                          ),

                          //Status label
                          SizedBox(
                            width: 140,
                            child: Text(
                              'Seat Status',
                              style: TextStyle(
                                color: Constants.textWhite80Color,
                              ),
                            ),
                          ),
                        ],
                      ),

                      const SizedBox(height: 10),

                      //Column data
                      Expanded(
                        child: ListView.separated(
                          itemCount: bookings.length,
                          padding: const EdgeInsets.all(0),
                          separatorBuilder: (ctx, i) =>
                              const SizedBox(height: 20),
                          itemBuilder: (ctx, i) => _BookingSeatsListItem(
                            booking: bookings[i],
                            ref: ref,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),

            //Expand icon
            Container(
              width: double.infinity,
              decoration: const BoxDecoration(
                color: Constants.primaryColor,
                borderRadius: BorderRadius.only(
                  bottomLeft: Radius.circular(20),
                  bottomRight: Radius.circular(20),
                ),
              ),
              child: const Icon(
                Icons.expand_more_sharp,
                color: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BookingSeatsListItem extends StatelessWidget {
  const _BookingSeatsListItem({
    Key? key,
    required this.booking,
    required this.ref,
  }) : super(key: key);

  final BookingModel booking;
  final WidgetRef ref;

  IconData get _statusIcon {
    if (booking.bookingStatus.isCancelled) return Icons.cancel_sharp;
    return Icons.confirmation_number_sharp;
  }

  Color get _statusIconColor {
    if (booking.bookingStatus.isCancelled) return Colors.red;
    return const Color(0xFF64DD17);
  }

  Future<void> _cancelBooking(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => const CustomDialog.confirm(
        title: 'Cancel booking?',
        body: 'This seat will be marked as cancelled.',
        falseButtonText: 'Keep',
        trueButtonText: 'Cancel',
      ),
    );
    if (confirmed != true || booking.bookingId == null) return;

    try {
      final messenger = ScaffoldMessenger.of(context);
      final navigator = Navigator.of(context);
      final message = await ref
          .read(bookingsProvider)
          .cancelBooking(bookingId: booking.bookingId!);
      ref.refresh(userBookingsProvider);
      if (navigator.canPop()) navigator.pop();
      messenger.showSnackBar(
        SnackBar(content: Text(message)),
      );
    } on Exception catch (error) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Booking could not be cancelled: $error')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final canCancel = booking.bookingStatus.canCancel;
    return Row(
      children: [
        //Seat Name
        SizedBox(
          width: 50,
          child: Text(
            '${booking.seatRow}-${booking.seatNumber}',
            style: const TextStyle(
              color: Constants.textGreyColor,
              fontSize: 13,
            ),
          ),
        ),

        //Seat Price
        Expanded(
          child: Text(
            "${booking.seatNumber == 3 ? "1000.0" : booking.price}",
            style: const TextStyle(
              color: Constants.textGreyColor,
              fontSize: 13,
            ),
          ),
        ),

        //Seat Status
        SizedBox(
          width: 140,
          child: Row(
            children: [
              //Booking Status value
              Expanded(
                child: Text(
                  booking.bookingStatus.displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Constants.textGreyColor,
                    fontSize: 13,
                  ),
                ),
              ),

              const SizedBox(width: 4),

              //Booking Status icon
              SizedBox(
                width: 18,
                child: Icon(
                  _statusIcon,
                  size: 16,
                  color: _statusIconColor,
                ),
              ),

              const SizedBox(width: 4),

              SizedBox(
                width: 44,
                child: canCancel
                    ? TappableIcon(
                        icon: Icons.delete_outline,
                        color: Colors.redAccent,
                        iconSize: 18,
                        size: 44,
                        tooltip: 'Cancel booking',
                        onTap: () => _cancelBooking(context),
                      )
                    : null,
              ),
            ],
          ),
        )
      ],
    );
  }
}
