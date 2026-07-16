import 'package:flutter/material.dart';
import 'package:flutter_hooks/flutter_hooks.dart';

//Widgets
import '../common/tappable_icon.dart';
import 'movie_type_popup_menu.dart';

class MoviesIconsRow extends HookWidget {
  const MoviesIconsRow({
    Key? key,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: SizedBox(
        height: 64,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              //Back Arrow
              TappableIcon(
                icon: Icons.arrow_back_rounded,
                onTap: () {
                  Navigator.of(context).maybePop();
                },
              ),

              //Filter
              const MovieTypePopupMenu(),
            ],
          ),
        ),
      ),
    );
  }
}
