import 'package:flutter/material.dart';

class TappableIcon extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final Color? color;
  final String? tooltip;
  final double iconSize;
  final double size;
  final BoxDecoration? decoration;

  const TappableIcon({
    Key? key,
    required this.icon,
    required this.onTap,
    this.color,
    this.tooltip,
    this.iconSize = 26,
    this.size = 48,
    this.decoration,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final button = GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: SizedBox.square(
        dimension: size,
        child: DecoratedBox(
          decoration: decoration ?? const BoxDecoration(),
          child: Center(
            child: Icon(
              icon,
              color: color,
              size: iconSize,
            ),
          ),
        ),
      ),
    );

    if (tooltip == null) return button;
    return Tooltip(message: tooltip!, child: button);
  }
}
