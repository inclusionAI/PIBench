import 'package:flutter/material.dart';

//Routing
import '../../../routes/app_router.dart';

//Helpers
import '../../../helper/utils/constants.dart';

import 'tappable_icon.dart';

class RoundedBottomContainer extends StatelessWidget {
  final List<Widget> children;
  final VoidCallback? onBackTap;
  final EdgeInsets? padding;
  final bool showBackButton;

  const RoundedBottomContainer({
    Key? key,
    required this.children,
    this.onBackTap,
    this.padding,
    this.showBackButton = true,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        color: Constants.scaffoldGreyColor,
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(25),
          bottomRight: Radius.circular(25),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (showBackButton)
            //back arrow
            Padding(
              padding: const EdgeInsets.only(left: 25.0 - 16, top: 28),
              child: TappableIcon(
                icon: Icons.arrow_back_sharp,
                iconSize: 32,
                color: Colors.white,
                onTap: onBackTap ?? () => AppRouter.pop(),
              ),
            ),
          Padding(
            padding: padding ?? const EdgeInsets.fromLTRB(25.0, 28, 25.0, 27),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: children,
            ),
          ),
        ],
      ),
    );
  }
}
